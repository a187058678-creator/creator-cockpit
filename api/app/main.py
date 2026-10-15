import os
import json
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import AssetRecord, TaskRecord, WorkerNode


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Creator Cockpit API", lifespan=lifespan)


TASK_PAYLOAD_SCHEMA_VERSION = "creator-task/v1"
ALLOWED_DEDUPE_PROFILES = {"light", "balanced", "aggressive"}


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, numeric))


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    return default


def ensure_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def deep_merge_dict(base: dict, updates: dict):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge_dict(base[key], value)
        else:
            base[key] = value


def get_dedupe_profile_defaults(profile: str) -> dict:
    normalized_profile = profile if profile in ALLOWED_DEDUPE_PROFILES else "balanced"
    presets = {
        "light": {
            "enabled": True,
            "profile": "light",
            "intensity": 0.35,
            "seed": 0,
            "randomize": True,
            "trim": {"head_seconds": 0.08, "tail_seconds": 0.05},
            "speed": {"min_factor": 1.005, "max_factor": 1.018},
            "crop": {"min_ratio": 0.988, "max_ratio": 0.998},
            "rotation": {"min_degrees": -0.2, "max_degrees": 0.2},
            "mirror_chance": 0.08,
            "color": {
                "brightness_min": 0.99,
                "brightness_max": 1.02,
                "contrast_min": -2.0,
                "contrast_max": 4.0,
            },
        },
        "balanced": {
            "enabled": True,
            "profile": "balanced",
            "intensity": 0.55,
            "seed": 0,
            "randomize": True,
            "trim": {"head_seconds": 0.18, "tail_seconds": 0.12},
            "speed": {"min_factor": 1.01, "max_factor": 1.035},
            "crop": {"min_ratio": 0.978, "max_ratio": 0.994},
            "rotation": {"min_degrees": -0.45, "max_degrees": 0.45},
            "mirror_chance": 0.15,
            "color": {
                "brightness_min": 0.97,
                "brightness_max": 1.04,
                "contrast_min": -4.0,
                "contrast_max": 8.0,
            },
        },
        "aggressive": {
            "enabled": True,
            "profile": "aggressive",
            "intensity": 0.8,
            "seed": 0,
            "randomize": True,
            "trim": {"head_seconds": 0.35, "tail_seconds": 0.22},
            "speed": {"min_factor": 1.015, "max_factor": 1.06},
            "crop": {"min_ratio": 0.965, "max_ratio": 0.99},
            "rotation": {"min_degrees": -0.9, "max_degrees": 0.9},
            "mirror_chance": 0.28,
            "color": {
                "brightness_min": 0.95,
                "brightness_max": 1.06,
                "contrast_min": -6.0,
                "contrast_max": 12.0,
            },
        },
    }
    return deepcopy(presets[normalized_profile])


def build_task_payload_defaults(profile: str = "balanced") -> dict:
    return {
        "schema_version": TASK_PAYLOAD_SCHEMA_VERSION,
        "source": {
            "asset_key": "",
            "start_seconds": 0.0,
            "end_seconds": 0.0,
        },
        "publish": {
            "platforms": [],
            "need_subtitles": False,
        },
        "output": {
            "prefix": "processed",
            "target_height": 720,
            "video_codec": "libx264",
            "audio_codec": "aac",
        },
        "execution": {
            "max_retries": 2,
            "simulate_fail": False,
        },
        "dedupe": get_dedupe_profile_defaults(profile),
    }


def normalize_task_payload(raw_payload: Any) -> dict:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    dedupe_section = payload.get("dedupe") if isinstance(payload.get("dedupe"), dict) else {}
    profile_hint = str(dedupe_section.get("profile") or payload.get("profile") or "balanced").strip().lower()
    defaults = build_task_payload_defaults(profile_hint)
    normalized = deepcopy(defaults)

    new_shape = {
        "schema_version": payload.get("schema_version", TASK_PAYLOAD_SCHEMA_VERSION),
        "source": payload.get("source") if isinstance(payload.get("source"), dict) else {},
        "publish": payload.get("publish") if isinstance(payload.get("publish"), dict) else {},
        "output": payload.get("output") if isinstance(payload.get("output"), dict) else {},
        "execution": payload.get("execution") if isinstance(payload.get("execution"), dict) else {},
        "dedupe": payload.get("dedupe") if isinstance(payload.get("dedupe"), dict) else {},
    }
    deep_merge_dict(normalized, new_shape)

    legacy_shape = {"source": {}, "publish": {}, "output": {}, "execution": {}, "dedupe": {}}
    if "asset_key" in payload:
        legacy_shape["source"]["asset_key"] = payload.get("asset_key")
    if "clip_start_seconds" in payload or "source_start_seconds" in payload:
        legacy_shape["source"]["start_seconds"] = payload.get("clip_start_seconds", payload.get("source_start_seconds"))
    if "clip_end_seconds" in payload or "source_end_seconds" in payload:
        legacy_shape["source"]["end_seconds"] = payload.get("clip_end_seconds", payload.get("source_end_seconds"))
    if "platforms" in payload:
        legacy_shape["publish"]["platforms"] = payload.get("platforms")
    if "need_subtitles" in payload:
        legacy_shape["publish"]["need_subtitles"] = payload.get("need_subtitles")
    if "output_prefix" in payload:
        legacy_shape["output"]["prefix"] = payload.get("output_prefix")
    if "target_height" in payload:
        legacy_shape["output"]["target_height"] = payload.get("target_height")
    if "max_retries" in payload:
        legacy_shape["execution"]["max_retries"] = payload.get("max_retries")
    if "simulate_fail" in payload:
        legacy_shape["execution"]["simulate_fail"] = payload.get("simulate_fail")
    if "profile" in payload:
        legacy_shape["dedupe"]["profile"] = payload.get("profile")
    if "trim_start_seconds" in payload:
        legacy_shape["dedupe"].setdefault("trim", {})["head_seconds"] = payload.get("trim_start_seconds")
    if "trim_end_seconds" in payload:
        legacy_shape["dedupe"].setdefault("trim", {})["tail_seconds"] = payload.get("trim_end_seconds")
    if "speed_factor" in payload:
        legacy_shape["dedupe"].setdefault("speed", {})["min_factor"] = payload.get("speed_factor")
        legacy_shape["dedupe"].setdefault("speed", {})["max_factor"] = payload.get("speed_factor")

    deep_merge_dict(normalized, legacy_shape)

    normalized["schema_version"] = TASK_PAYLOAD_SCHEMA_VERSION
    normalized["source"]["asset_key"] = str(normalized["source"].get("asset_key") or "").strip()
    normalized["source"]["start_seconds"] = clamp_float(
        normalized["source"].get("start_seconds"),
        0.0,
        0.0,
        86400.0,
    )
    normalized["source"]["end_seconds"] = clamp_float(
        normalized["source"].get("end_seconds"),
        0.0,
        0.0,
        86400.0,
    )
    if normalized["source"]["end_seconds"] and normalized["source"]["end_seconds"] < normalized["source"]["start_seconds"]:
        normalized["source"]["end_seconds"] = normalized["source"]["start_seconds"]

    normalized["publish"]["platforms"] = ensure_str_list(normalized["publish"].get("platforms"))
    normalized["publish"]["need_subtitles"] = coerce_bool(
        normalized["publish"].get("need_subtitles"),
        False,
    )

    normalized["output"]["prefix"] = str(normalized["output"].get("prefix") or "processed").strip("/") or "processed"
    normalized["output"]["target_height"] = clamp_int(
        normalized["output"].get("target_height"),
        720,
        240,
        2160,
    )
    normalized["output"]["video_codec"] = str(normalized["output"].get("video_codec") or "libx264").strip() or "libx264"
    normalized["output"]["audio_codec"] = str(normalized["output"].get("audio_codec") or "aac").strip() or "aac"

    normalized["execution"]["max_retries"] = clamp_int(
        normalized["execution"].get("max_retries"),
        2,
        0,
        10,
    )
    normalized["execution"]["simulate_fail"] = coerce_bool(
        normalized["execution"].get("simulate_fail"),
        False,
    )

    normalized_profile = str(normalized["dedupe"].get("profile") or "balanced").strip().lower()
    if normalized_profile not in ALLOWED_DEDUPE_PROFILES:
        normalized_profile = "balanced"
    normalized["dedupe"]["profile"] = normalized_profile
    normalized["dedupe"]["enabled"] = coerce_bool(normalized["dedupe"].get("enabled"), True)
    normalized["dedupe"]["intensity"] = clamp_float(normalized["dedupe"].get("intensity"), 0.55, 0.0, 1.0)
    normalized["dedupe"]["seed"] = clamp_int(normalized["dedupe"].get("seed"), 0, 0, 2147483647)
    normalized["dedupe"]["randomize"] = coerce_bool(normalized["dedupe"].get("randomize"), True)
    normalized["dedupe"]["mirror_chance"] = clamp_float(
        normalized["dedupe"].get("mirror_chance"),
        defaults["dedupe"]["mirror_chance"],
        0.0,
        1.0,
    )

    trim = normalized["dedupe"].setdefault("trim", {})
    trim["head_seconds"] = clamp_float(trim.get("head_seconds"), defaults["dedupe"]["trim"]["head_seconds"], 0.0, 30.0)
    trim["tail_seconds"] = clamp_float(trim.get("tail_seconds"), defaults["dedupe"]["trim"]["tail_seconds"], 0.0, 30.0)

    speed = normalized["dedupe"].setdefault("speed", {})
    speed["min_factor"] = clamp_float(speed.get("min_factor"), defaults["dedupe"]["speed"]["min_factor"], 0.9, 1.2)
    speed["max_factor"] = clamp_float(speed.get("max_factor"), defaults["dedupe"]["speed"]["max_factor"], 0.9, 1.2)
    if speed["min_factor"] > speed["max_factor"]:
        speed["min_factor"], speed["max_factor"] = speed["max_factor"], speed["min_factor"]

    crop = normalized["dedupe"].setdefault("crop", {})
    crop["min_ratio"] = clamp_float(crop.get("min_ratio"), defaults["dedupe"]["crop"]["min_ratio"], 0.9, 1.0)
    crop["max_ratio"] = clamp_float(crop.get("max_ratio"), defaults["dedupe"]["crop"]["max_ratio"], 0.9, 1.0)
    if crop["min_ratio"] > crop["max_ratio"]:
        crop["min_ratio"], crop["max_ratio"] = crop["max_ratio"], crop["min_ratio"]

    rotation = normalized["dedupe"].setdefault("rotation", {})
    rotation["min_degrees"] = clamp_float(
        rotation.get("min_degrees"),
        defaults["dedupe"]["rotation"]["min_degrees"],
        -3.0,
        3.0,
    )
    rotation["max_degrees"] = clamp_float(
        rotation.get("max_degrees"),
        defaults["dedupe"]["rotation"]["max_degrees"],
        -3.0,
        3.0,
    )
    if rotation["min_degrees"] > rotation["max_degrees"]:
        rotation["min_degrees"], rotation["max_degrees"] = rotation["max_degrees"], rotation["min_degrees"]

    color = normalized["dedupe"].setdefault("color", {})
    color["brightness_min"] = clamp_float(
        color.get("brightness_min"),
        defaults["dedupe"]["color"]["brightness_min"],
        0.85,
        1.15,
    )
    color["brightness_max"] = clamp_float(
        color.get("brightness_max"),
        defaults["dedupe"]["color"]["brightness_max"],
        0.85,
        1.15,
    )
    if color["brightness_min"] > color["brightness_max"]:
        color["brightness_min"], color["brightness_max"] = color["brightness_max"], color["brightness_min"]
    color["contrast_min"] = clamp_float(
        color.get("contrast_min"),
        defaults["dedupe"]["color"]["contrast_min"],
        -20.0,
        20.0,
    )
    color["contrast_max"] = clamp_float(
        color.get("contrast_max"),
        defaults["dedupe"]["color"]["contrast_max"],
        -20.0,
        20.0,
    )
    if color["contrast_min"] > color["contrast_max"]:
        color["contrast_min"], color["contrast_max"] = color["contrast_max"], color["contrast_min"]

    return normalized


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
    payload: dict = Field(default_factory=dict)


class WorkerHeartbeatRequest(BaseModel):
    worker_code: str
    display_name: str
    status: str = "idle"
    machine_info: str = ""
    capabilities: list[str] = []
    current_task_title: str = ""
    heartbeat_note: str = ""


class UpdateTaskRequest(BaseModel):
    status: Optional[str] = None
    assigned_worker_code: Optional[str] = None
    result: Optional[dict] = None


class WorkerTaskClaimRequest(BaseModel):
    worker_code: str


class WorkerTaskCompleteRequest(BaseModel):
    worker_code: str
    result: dict = Field(default_factory=dict)


class WorkerTaskFailRequest(BaseModel):
    worker_code: str
    error_message: str
    retryable: bool = True
    result: dict = Field(default_factory=dict)


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


def get_worker_offline_timeout_seconds() -> int:
    raw_value = os.getenv("WORKER_OFFLINE_TIMEOUT_SECONDS", "180")
    try:
        return max(30, int(raw_value))
    except ValueError:
        return 180


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


def ensure_asset_record_from_result(db: Session, task: TaskRecord, result: dict):
    asset = result.get("asset") if isinstance(result, dict) else None
    if not asset:
        return None

    asset_key = asset.get("key")
    if not asset_key:
        return None

    existing = db.scalar(select(AssetRecord).where(AssetRecord.asset_key == asset_key))
    if existing:
        return existing

    return create_asset_record(
        db,
        source_type=asset.get("source_type", "worker"),
        bucket=asset.get("bucket", get_bucket_name()),
        key=asset_key,
        prefix=asset.get("prefix", "processed"),
        original_filename=asset.get("original_filename", task.title),
        stored_filename=asset.get("stored_filename", asset_key.split("/")[-1]),
        content_type=asset.get("content_type", "video/mp4"),
        size_bytes=int(asset.get("size_bytes", 0)),
        storage_url=asset.get("storage_url", build_object_url(asset_key)),
    )


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


def load_json_field(raw_value: str, fallback):
    try:
        return json.loads(raw_value or "")
    except json.JSONDecodeError:
        return fallback


def utcnow():
    return datetime.now(timezone.utc)


def iso_now():
    return utcnow().isoformat()


def get_task_runtime_state(record: TaskRecord):
    state = load_json_field(record.result_json, {})
    state.setdefault("attempt_count", 0)
    state.setdefault("retry_count", 0)
    state.setdefault("manual_retry_count", 0)
    state.setdefault("max_retries", 2)
    state.setdefault("last_error", "")
    state.setdefault("history", [])
    return state


def save_task_runtime_state(record: TaskRecord, state: dict):
    record.result_json = json.dumps(state, ensure_ascii=False)


def append_task_history(state: dict, event: str, **extra):
    history = state.setdefault("history", [])
    history.append({"event": event, "at": iso_now(), **extra})
    if len(history) > 20:
        del history[:-20]


def serialize_task_record(record: TaskRecord):
    runtime_state = get_task_runtime_state(record)
    task_payload = normalize_task_payload(load_json_field(record.payload_json, {}))
    return {
        "id": record.id,
        "title": record.title,
        "task_type": record.task_type,
        "source_type": record.source_type,
        "source_value": record.source_value,
        "status": record.status,
        "priority": record.priority,
        "assigned_worker_code": record.assigned_worker_code,
        "payload": task_payload,
        "result": runtime_state,
        "attempt_count": runtime_state.get("attempt_count", 0),
        "retry_count": runtime_state.get("retry_count", 0),
        "manual_retry_count": runtime_state.get("manual_retry_count", 0),
        "max_retries": runtime_state.get("max_retries", 2),
        "last_error": runtime_state.get("last_error", ""),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def get_effective_worker_status(record: WorkerNode) -> str:
    if not record.last_heartbeat_at:
        return "offline"

    heartbeat_at = record.last_heartbeat_at
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)

    timeout_at = heartbeat_at + timedelta(seconds=get_worker_offline_timeout_seconds())
    now = datetime.now(timezone.utc)
    if timeout_at < now:
        return "offline"
    return record.status


def serialize_worker_node(record: WorkerNode):
    effective_status = get_effective_worker_status(record)
    return {
        "id": record.id,
        "worker_code": record.worker_code,
        "display_name": record.display_name,
        "status": effective_status,
        "reported_status": record.status,
        "machine_info": record.machine_info,
        "capabilities": json.loads(record.capabilities or "[]"),
        "current_task_title": record.current_task_title,
        "heartbeat_note": record.heartbeat_note,
        "last_heartbeat_at": record.last_heartbeat_at.isoformat() if record.last_heartbeat_at else None,
        "is_timed_out": effective_status == "offline" and record.status != "offline",
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def set_worker_idle_if_online(record: WorkerNode, note: str):
    record.current_task_title = ""
    if get_effective_worker_status(record) != "offline":
        record.status = "idle"
    record.heartbeat_note = note


def get_worker_or_404(db: Session, worker_code: str) -> WorkerNode:
    record = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == worker_code))
    if not record:
        raise HTTPException(status_code=404, detail="指定的 Worker 不存在")
    return record


def get_task_or_404(db: Session, task_id: int) -> TaskRecord:
    record = db.scalar(select(TaskRecord).where(TaskRecord.id == task_id))
    if not record:
        raise HTTPException(status_code=404, detail="任务不存在")
    return record


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
    worker_items = db.scalars(select(WorkerNode).order_by(desc(WorkerNode.id))).all()
    online_workers = len(
        [item for item in worker_items if get_effective_worker_status(item) in ["idle", "running", "online"]]
    )
    latest_task = db.scalar(select(TaskRecord).order_by(desc(TaskRecord.id)).limit(1))
    latest_worker = worker_items[0] if worker_items else None
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
    normalized_payload = normalize_task_payload(payload.payload)
    runtime_state = {
        "attempt_count": 0,
        "retry_count": 0,
        "manual_retry_count": 0,
        "max_retries": normalized_payload["execution"]["max_retries"],
        "last_error": "",
        "history": [],
    }
    append_task_history(runtime_state, "created", source_type=payload.source_type)
    record = TaskRecord(
        title=payload.title,
        task_type=payload.task_type,
        source_type=payload.source_type,
        source_value=payload.source_value,
        status="pending",
        priority=payload.priority,
        payload_json=json.dumps(normalized_payload, ensure_ascii=False),
        result_json=json.dumps(runtime_state, ensure_ascii=False),
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
    failed = db.scalar(
        select(func.count()).select_from(TaskRecord).where(TaskRecord.status == "failed")
    ) or 0
    latest = db.scalar(select(TaskRecord).order_by(desc(TaskRecord.id)).limit(1))
    return {
        "ok": True,
        "total": total,
        "pending": pending,
        "running": running,
        "success": success,
        "failed": failed,
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
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(record)
    else:
        record.display_name = payload.display_name
        record.status = payload.status
        record.machine_info = payload.machine_info
        record.capabilities = json.dumps(payload.capabilities, ensure_ascii=False)
        record.current_task_title = payload.current_task_title
        record.heartbeat_note = payload.heartbeat_note
        record.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_worker_node(record)}


@app.get("/workers")
def list_workers(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    items = db.scalars(select(WorkerNode).order_by(desc(WorkerNode.id)).limit(limit)).all()
    return {"ok": True, "items": [serialize_worker_node(item) for item in items]}


@app.delete("/workers/{worker_code}")
def delete_worker(worker_code: str, db: Session = Depends(get_db)):
    worker = get_worker_or_404(db, worker_code)

    running_task = db.scalar(
        select(TaskRecord)
        .where(
            TaskRecord.assigned_worker_code == worker_code,
            TaskRecord.status == "running",
        )
        .limit(1)
    )
    if running_task:
        raise HTTPException(status_code=409, detail="该 Worker 正在执行任务，不能直接删除")

    assigned_tasks = db.scalars(
        select(TaskRecord).where(TaskRecord.assigned_worker_code == worker_code)
    ).all()
    for task in assigned_tasks:
        task.assigned_worker_code = ""

    deleted_item = serialize_worker_node(worker)
    db.delete(worker)
    db.commit()
    return {"ok": True, "item": deleted_item, "cleared_task_count": len(assigned_tasks)}


@app.get("/workers/summary")
def workers_summary(db: Session = Depends(get_db)):
    items = db.scalars(select(WorkerNode).order_by(desc(WorkerNode.id))).all()
    total = len(items)
    online = len([item for item in items if get_effective_worker_status(item) in ["idle", "running", "online"]])
    offline = total - online
    latest = items[0] if items else None
    return {
        "ok": True,
        "total": total,
        "online": online,
        "offline": offline,
        "latest": serialize_worker_node(latest) if latest else None,
    }


@app.patch("/tasks/{task_id}")
def update_task(task_id: int, payload: UpdateTaskRequest, db: Session = Depends(get_db)):
    record = get_task_or_404(db, task_id)

    previous_worker_code = record.assigned_worker_code
    worker_record = None
    if payload.assigned_worker_code is not None:
        normalized_worker_code = payload.assigned_worker_code.strip()
        if normalized_worker_code:
            worker_record = db.scalar(
                select(WorkerNode).where(WorkerNode.worker_code == normalized_worker_code)
            )
            if not worker_record:
                raise HTTPException(status_code=404, detail="指定的 Worker 不存在")
            record.assigned_worker_code = normalized_worker_code
        else:
            record.assigned_worker_code = ""

    if payload.status is not None:
        record.status = payload.status.strip() or record.status

    if payload.result is not None:
        save_task_runtime_state(record, payload.result)

    if previous_worker_code and previous_worker_code != record.assigned_worker_code:
        previous_worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == previous_worker_code))
        if previous_worker:
            previous_worker.current_task_title = ""
            if get_effective_worker_status(previous_worker) != "offline":
                previous_worker.status = "idle"
            previous_worker.heartbeat_note = f"已取消任务 #{record.id} 指派"

    assigned_worker = None
    if record.assigned_worker_code:
        assigned_worker = db.scalar(
            select(WorkerNode).where(WorkerNode.worker_code == record.assigned_worker_code)
        )

    if assigned_worker:
        if record.status == "running":
            assigned_worker.status = "running"
            assigned_worker.current_task_title = record.title
            assigned_worker.heartbeat_note = f"处理中：任务 #{record.id}"
        elif record.status in ["success", "failed", "cancelled", "pending", "queued"]:
            assigned_worker.current_task_title = ""
            if get_effective_worker_status(assigned_worker) != "offline":
                assigned_worker.status = "idle"
            assigned_worker.heartbeat_note = f"最近处理任务 #{record.id} 状态：{record.status}"

    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_task_record(record)}


@app.post("/worker/tasks/claim")
def claim_task(payload: WorkerTaskClaimRequest, db: Session = Depends(get_db)):
    worker = get_worker_or_404(db, payload.worker_code)
    current_running_task = db.scalar(
        select(TaskRecord)
        .where(
            TaskRecord.assigned_worker_code == payload.worker_code,
            TaskRecord.status == "running",
        )
        .order_by(desc(TaskRecord.id))
        .limit(1)
    )
    if current_running_task:
        return {"ok": True, "item": serialize_task_record(current_running_task), "reused": True}

    task = db.scalar(
        select(TaskRecord)
        .where(
            TaskRecord.status.in_(["pending", "queued"]),
        )
        .order_by(
            case((TaskRecord.priority == "high", 0), else_=1),
            TaskRecord.id,
        )
        .limit(1)
    )
    if not task:
        if get_effective_worker_status(worker) != "offline":
            worker.status = "idle"
            worker.current_task_title = ""
            worker.heartbeat_note = "暂无可领取任务"
            db.commit()
        return {"ok": True, "item": None}

    state = get_task_runtime_state(task)
    state["attempt_count"] = int(state.get("attempt_count", 0)) + 1
    state["last_error"] = ""
    append_task_history(state, "claimed", worker_code=payload.worker_code)
    save_task_runtime_state(task, state)

    task.status = "running"
    task.assigned_worker_code = payload.worker_code
    worker.status = "running"
    worker.current_task_title = task.title
    worker.heartbeat_note = f"已领取任务 #{task.id}"
    worker.last_heartbeat_at = utcnow()
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task), "reused": False}


@app.post("/worker/tasks/{task_id}/complete")
def complete_task(task_id: int, payload: WorkerTaskCompleteRequest, db: Session = Depends(get_db)):
    task = get_task_or_404(db, task_id)
    if task.assigned_worker_code != payload.worker_code:
        raise HTTPException(status_code=409, detail="该任务未分配给当前 Worker")

    worker = get_worker_or_404(db, payload.worker_code)
    state = get_task_runtime_state(task)
    state["last_error"] = ""
    state["output"] = payload.result
    append_task_history(state, "completed", worker_code=payload.worker_code)
    save_task_runtime_state(task, state)

    task.status = "success"
    ensure_asset_record_from_result(db, task, payload.result)
    set_worker_idle_if_online(worker, f"最近完成任务 #{task.id}")
    worker.last_heartbeat_at = utcnow()
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task)}


@app.post("/worker/tasks/{task_id}/fail")
def fail_task(task_id: int, payload: WorkerTaskFailRequest, db: Session = Depends(get_db)):
    task = get_task_or_404(db, task_id)
    if task.assigned_worker_code != payload.worker_code:
        raise HTTPException(status_code=409, detail="该任务未分配给当前 Worker")

    worker = get_worker_or_404(db, payload.worker_code)
    state = get_task_runtime_state(task)
    max_retries = int(state.get("max_retries", 2))
    next_retry_count = int(state.get("retry_count", 0))
    will_retry = payload.retryable and next_retry_count < max_retries

    if will_retry:
        next_retry_count += 1
        state["retry_count"] = next_retry_count
        task.status = "queued"
        task.assigned_worker_code = ""
    else:
        task.status = "failed"

    state["last_error"] = payload.error_message
    if payload.result:
        state["output"] = payload.result
    append_task_history(
        state,
        "failed" if not will_retry else "retry_queued",
        worker_code=payload.worker_code,
        retryable=payload.retryable,
        retry_count=state.get("retry_count", 0),
        error_message=payload.error_message,
    )
    save_task_runtime_state(task, state)

    set_worker_idle_if_online(
        worker,
        f"任务 #{task.id} {'已进入重试队列' if will_retry else '执行失败'}",
    )
    worker.last_heartbeat_at = utcnow()
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task), "will_retry": will_retry}


@app.post("/tasks/{task_id}/retry")
def retry_task(task_id: int, db: Session = Depends(get_db)):
    task = get_task_or_404(db, task_id)
    state = get_task_runtime_state(task)
    state["manual_retry_count"] = int(state.get("manual_retry_count", 0)) + 1
    state["last_error"] = ""
    append_task_history(state, "manual_retry")
    save_task_runtime_state(task, state)

    if task.assigned_worker_code:
        worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == task.assigned_worker_code))
        if worker:
            set_worker_idle_if_online(worker, f"任务 #{task.id} 已手动重试")

    task.assigned_worker_code = ""
    task.status = "queued"
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task)}
