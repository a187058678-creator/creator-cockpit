import os
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException

app = FastAPI()

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/r2/test-upload")
def r2_test_upload():
    bucket = os.environ["S3_BUCKET"]
    key = f"temp/r2-smoke-test-{uuid.uuid4().hex}.txt"
    body = b"hello from railway fastapi to cloudflare r2"

    try:
        client = get_s3_client()
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="text/plain; charset=utf-8",
        )
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "endpoint": os.environ["S3_ENDPOINT"],
        }
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Missing env var: {e.args[0]}")
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))
