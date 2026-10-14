import os
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import AssetRecord, TaskRecord, WorkerNode


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Creator Cockpit API", lifespan=lifespan)


class UploadTextRequest(BaseModel):
    text: str
    prefix: str = "assets"
    filename: Optional[str] = None


class CreateTaskRequest(BaseModel):
    title: str
    task_type: str = "publish"
    source_type: str = "manual"
    source_value: str = ""
    priority: str = "normal"
    payload: dict = {}


class WorkerHeartbeatRequest(BaseModel):
    worker_code: str
    display_name: str
    status: str = "idle"
    machine_info: str = ""
    capabilities: list[str] = []
    current_task_title: str = ""
    heartbeat_note: str = ""


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")
    return value


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=get_required_env("S3_ENDPOINT"),
        aws_access_key_id=get_required_env("S3_ACCESS_KEY"),
        aws_secret_access_key=get_required_env("S3_SECRET_KEY"),
        region_name=os.getenv("S3_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )


def get_bucket_name() -> str:
    return get_required_env("S3_BUCKET")


def build_object_url(key: str) -> str:
    endpoint = get_required_env("S3_ENDPOINT").rstrip("/")
    bucket = get_bucket_name()
    return f"{endpoint}/{bucket}/{key}"


def create_asset_record(
    db: Session,
    *,
    source_type: str,
    bucket: str,
    key: str,
    prefix: str,
    original_filename: str,
    stored_filename: str,
    content_type: str,
    size_bytes: int,
    storage_url: str,
):
    record = AssetRecord(
        source_type=source_type,
        bucket=bucket,
        asset_key=key,
        prefix=prefix,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_url=storage_url,
        status="uploaded",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def serialize_asset_record(record: AssetRecord):
    return {
        "id": record.id,
        "source_type": record.source_type,
        "bucket": record.bucket,
        "key": record.asset_key,
        "prefix": record.prefix,
        "original_filename": record.original_filename,
        "stored_filename": record.stored_filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "storage_url": record.storage_url,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def serialize_task_record(record: TaskRecord):
    return {
        "id": record.id,
        "title": record.title,
        "task_type": record.task_type,
        "source_type": record.source_type,
        "source_value": record.source_value,
        "status": record.status,
        "priority": record.priority,
        "assigned_worker_code": record.assigned_worker_code,
        "payload": json.loads(record.payload_json or "{}"),
        "result": json.loads(record.result_json or "{}"),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def serialize_worker_node(record: WorkerNode):
    return {
        "id": record.id,
        "worker_code": record.worker_code,
        "display_name": record.display_name,
        "status": record.status,
        "machine_info": record.machine_info,
        "capabilities": json.loads(record.capabilities or "[]"),
        "current_task_title": record.current_task_title,
        "heartbeat_note": record.heartbeat_note,
        "last_heartbeat_at": record.last_heartbeat_at.isoformat() if record.last_heartbeat_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    total_records = db.scalar(select(func.count()).select_from(AssetRecord)) or 0
    return {"ok": True, "asset_records": total_records}


@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    total_records = db.scalar(select(func.count()).select_from(AssetRecord)) or 0
    latest_record = db.scalar(select(AssetRecord).order_by(desc(AssetRecord.id)).limit(1))
    total_tasks = db.scalar(select(func.count()).select_from(TaskRecord)) or 0
    pending_tasks = db.scalar(
        select(func.count()).select_from(TaskRecord).where(TaskRecord.status.in_(["pending", "queued"]))
    ) or 0
    online_workers = db.scalar(
        select(func.count()).select_from(WorkerNode).where(WorkerNode.status.in_(["idle", "running", "online"]))
    ) or 0
    latest_task = db.scalar(select(TaskRecord).order_by(desc(TaskRecord.id)).limit(1))
    latest_worker = db.scalar(select(WorkerNode).order_by(desc(WorkerNode.id)).limit(1))
    return {
        "ok": True,
        "bucket": os.getenv("S3_BUCKET"),
        "storage_configured": bool(os.getenv("S3_BUCKET") and os.getenv("S3_ENDPOINT")),
        "database_configured": bool(os.getenv("DATABASE_URL")),
        "total_asset_records": total_records,
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "online_workers": online_workers,
        "latest_asset_record": serialize_asset_record(latest_record) if latest_record else None,
        "latest_task": serialize_task_record(latest_task) if latest_task else None,
        "latest_worker": serialize_worker_node(latest_worker) if latest_worker else None,
    }


@app.post("/assets/upload-text")
def upload_text(payload: UploadTextRequest, db: Session = Depends(get_db)):
    client = get_s3_client()
    bucket = get_bucket_name()

    filename = payload.filename or f"{uuid.uuid4().hex}.txt"
    prefix = payload.prefix.strip("/") or "assets"
    key = f"{prefix}/{filename}"
    body = payload.text.encode("utf-8")
    storage_url = build_object_url(key)

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="text/plain; charset=utf-8",
        )
        record = create_asset_record(
            db,
            source_type="text",
            bucket=bucket,
            key=key,
            prefix=prefix,
            original_filename=filename,
            stored_filename=filename,
            content_type="text/plain; charset=utf-8",
            size_bytes=len(body),
            storage_url=storage_url,
        )
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "url": storage_url,
            "record": serialize_asset_record(record),
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/assets/upload-file")
async def upload_file(
    file: UploadFile = File(...),
    prefix: str = Query("assets"),
    db: Session = Depends(get_db),
):
    client = get_s3_client()
    bucket = get_bucket_name()

    normalized_prefix = prefix.strip("/") or "assets"
    original_name = file.filename or "upload.bin"
    safe_name = f"{uuid.uuid4().hex}-{original_name}"
    key = f"{normalized_prefix}/{safe_name}"
    storage_url = build_object_url(key)

    try:
        content = await file.read()
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        record = create_asset_record(
            db,
            source_type="file",
            bucket=bucket,
            key=key,
            prefix=normalized_prefix,
            original_filename=original_name,
            stored_filename=safe_name,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
            storage_url=storage_url,
        )
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "filename": original_name,
            "content_type": file.content_type,
            "size": len(content),
            "url": storage_url,
            "record": serialize_asset_record(record),
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await file.close()


@app.get("/assets/list")
def list_assets(
    prefix: str = Query("assets"),
    limit: int = Query(20, ge=1, le=100),
):
    client = get_s3_client()
    bucket = get_bucket_name()
    normalized_prefix = prefix.strip("/")

    try:
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{normalized_prefix}/" if normalized_prefix else "",
            MaxKeys=limit,
        )
        items = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            items.append(
                {
                    "key": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "url": build_object_url(key),
                }
            )

        return {
            "ok": True,
            "bucket": bucket,
            "prefix": normalized_prefix,
            "items": items,
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/assets/records")
def list_asset_records(
    prefix: str = Query("assets"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    normalized_prefix = prefix.strip("/")
    statement = (
        select(AssetRecord)
        .where(AssetRecord.prefix == normalized_prefix)
        .order_by(desc(AssetRecord.id))
        .limit(limit)
    )
    records = db.scalars(statement).all()
    return {
        "ok": True,
        "prefix": normalized_prefix,
        "items": [serialize_asset_record(record) for record in records],
    }


@app.get("/assets/presign")
def presign_get_url(
    key: str,
    expires_in: int = Query(3600, ge=60, le=86400),
):
    client = get_s3_client()
    bucket = get_bucket_name()

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "expires_in": expires_in,
            "url": url,
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/assets")
def delete_asset(key: str, db: Session = Depends(get_db)):
    client = get_s3_client()
    bucket = get_bucket_name()

    try:
        client.delete_object(Bucket=bucket, Key=key)
        record = db.scalar(
            select(AssetRecord).where(AssetRecord.asset_key == key).order_by(desc(AssetRecord.id))
        )
        if record:
            record.status = "deleted"
            db.commit()
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "deleted": True,
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks")
def create_task(payload: CreateTaskRequest, db: Session = Depends(get_db)):
    record = TaskRecord(
        title=payload.title,
        task_type=payload.task_type,
        source_type=payload.source_type,
        source_value=payload.source_value,
        status="pending",
        priority=payload.priority,
        payload_json=json.dumps(payload.payload, ensure_ascii=False),
        result_json="{}",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_task_record(record)}


@app.get("/tasks")
def list_tasks(
    status: str = Query("", description="按状态过滤"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = select(TaskRecord).order_by(desc(TaskRecord.id)).limit(limit)
    if status:
        statement = (
            select(TaskRecord)
            .where(TaskRecord.status == status)
            .order_by(desc(TaskRecord.id))
            .limit(limit)
        )
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_task_record(item) for item in items]}


@app.get("/tasks/summary")
def tasks_summary(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(TaskRecord)) or 0
    pending = db.scalar(
        select(func.count()).select_from(TaskRecord).where(TaskRecord.status.in_(["pending", "queued"]))
    ) or 0
    running = db.scalar(
        select(func.count()).select_from(TaskRecord).where(TaskRecord.status == "running")
    ) or 0
    success = db.scalar(
        select(func.count()).select_from(TaskRecord).where(TaskRecord.status == "success")
    ) or 0
    latest = db.scalar(select(TaskRecord).order_by(desc(TaskRecord.id)).limit(1))
    return {
        "ok": True,
        "total": total,
        "pending": pending,
        "running": running,
        "success": success,
        "latest": serialize_task_record(latest) if latest else None,
    }


@app.post("/workers/heartbeat")
def worker_heartbeat(payload: WorkerHeartbeatRequest, db: Session = Depends(get_db)):
    record = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == payload.worker_code))
    if not record:
        record = WorkerNode(
            worker_code=payload.worker_code,
            display_name=payload.display_name,
            status=payload.status,
            machine_info=payload.machine_info,
            capabilities=json.dumps(payload.capabilities, ensure_ascii=False),
            current_task_title=payload.current_task_title,
            heartbeat_note=payload.heartbeat_note,
        )
        db.add(record)
    else:
        record.display_name = payload.display_name
        record.status = payload.status
        record.machine_info = payload.machine_info
        record.capabilities = json.dumps(payload.capabilities, ensure_ascii=False)
        record.current_task_title = payload.current_task_title
        record.heartbeat_note = payload.heartbeat_note
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_worker_node(record)}


@app.get("/workers")
def list_workers(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    items = db.scalars(select(WorkerNode).order_by(desc(WorkerNode.id)).limit(limit)).all()
    return {"ok": True, "items": [serialize_worker_node(item) for item in items]}


@app.get("/workers/summary")
def workers_summary(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(WorkerNode)) or 0
    online = db.scalar(
        select(func.count()).select_from(WorkerNode).where(WorkerNode.status.in_(["idle", "running", "online"]))
    ) or 0
    offline = db.scalar(
        select(func.count()).select_from(WorkerNode).where(WorkerNode.status == "offline")
    ) or 0
    latest = db.scalar(select(WorkerNode).order_by(desc(WorkerNode.id)).limit(1))
    return {
        "ok": True,
        "total": total,
        "online": online,
        "offline": offline,
        "latest": serialize_worker_node(latest) if latest else None,
    }
