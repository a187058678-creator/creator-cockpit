import os
import uuid
from datetime import timedelta
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

app = FastAPI(title="Creator Cockpit API")

class UploadTextRequest(BaseModel):
    text: str
    prefix: str = "assets"
    filename: Optional[str] = None

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

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/assets/upload-text")
def upload_text(payload: UploadTextRequest):
    client = get_s3_client()
    bucket = get_bucket_name()

    filename = payload.filename or f"{uuid.uuid4().hex}.txt"
    key = f"{payload.prefix.strip('/')}/{filename}"

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=payload.text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "url": build_object_url(key),
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/assets/upload-file")
async def upload_file(
    file: UploadFile = File(...),
    prefix: str = Query("assets"),
):
    client = get_s3_client()
    bucket = get_bucket_name()

    original_name = file.filename or "upload.bin"
    safe_name = f"{uuid.uuid4().hex}-{original_name}"
    key = f"{prefix.strip('/')}/{safe_name}"

    try:
        content = await file.read()
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "filename": original_name,
            "content_type": file.content_type,
            "size": len(content),
            "url": build_object_url(key),
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await file.close()

@app.get("/assets/list")
def list_assets(prefix: str = Query("assets"), limit: int = Query(20, ge=1, le=100)):
    client = get_s3_client()
    bucket = get_bucket_name()

    try:
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix.strip("/") + "/",
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
            "prefix": prefix,
            "items": items,
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))

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
def delete_asset(key: str):
    client = get_s3_client()
    bucket = get_bucket_name()

    try:
        client.delete_object(Bucket=bucket, Key=key)
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "deleted": True,
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))
