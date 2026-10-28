import os
import json
import uuid
import base64
import hashlib
import secrets
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import (
    AccountGroup,
    AssetRecord,
    AuditLog,
    OAuthSession,
    PlatformAccount,
    TaskRecord,
    TaskExecutionRecord,
    UserAccount,
    UserGroupMember,
    UserSession,
    WorkflowAsset,
    WorkflowAssetBundle,
    WorkflowPublishLink,
    WorkflowProject,
    WorkflowRun,
    WorkflowRunStage,
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkerNode,
    WorkerToken,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Creator Cockpit API", lifespan=lifespan)


TASK_PAYLOAD_SCHEMA_VERSION = "creator-task/v1"
ALLOWED_DEDUPE_PROFILES = {"light", "balanced", "aggressive"}
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v23.0")
SUPPORTED_PLATFORM_CODES = ["tiktok", "youtube", "facebook", "instagram", "x"]
POST_FOR_ME_BASE_URL = os.getenv("POST_FOR_ME_BASE_URL", "https://api.postforme.dev/v1").rstrip("/")
POST_FOR_ME_DEFAULT_API_KEY = os.getenv("POST_FOR_ME_DEFAULT_API_KEY", "pfm_live_B3ER8EQnwSegCteqWkhymm").strip()
PUBLIC_BUSINESS_API_MODE = str(os.getenv("PUBLIC_BUSINESS_API_MODE", "1")).strip().lower() in {"1", "true", "yes", "on"}
PUBLIC_TEST_GROUP_CODE = os.getenv("PUBLIC_TEST_GROUP_CODE", "public-test").strip() or "public-test"
PUBLIC_TEST_GROUP_NAME = os.getenv("PUBLIC_TEST_GROUP_NAME", "默认测试组").strip() or "默认测试组"


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
            "required_capabilities": [],
            "preferred_worker_codes": [],
            "lease_timeout_seconds": get_task_lease_timeout_seconds(),
        },
        "agent_flow": {
            "goal": "选题/提示词优化/发布文案生成",
            "topic_seed": "",
            "platform": "tiktok",
            "audience": "",
            "tone": "短视频爆款",
            "language": "zh-CN",
            "reference_prompt": "",
            "reference_copy": "",
            "deepseek": {
                "enabled": True,
                "model": "deepseek-chat",
                "temperature": 0.8,
                "max_topics": 5,
            },
            "video": {
                "enabled": False,
                "provider": "agnes",
                "model": "agnes-video-2.5-flash",
                "seconds": "5",
                "size": "1280x720",
                "poll_timeout_seconds": 120,
                "poll_interval_seconds": 10,
            },
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
        "agent_flow": payload.get("agent_flow") if isinstance(payload.get("agent_flow"), dict) else {},
        "dedupe": payload.get("dedupe") if isinstance(payload.get("dedupe"), dict) else {},
    }
    deep_merge_dict(normalized, new_shape)

    legacy_shape = {"source": {}, "publish": {}, "output": {}, "execution": {}, "agent_flow": {}, "dedupe": {}}
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
    if "required_capabilities" in payload:
        legacy_shape["execution"]["required_capabilities"] = payload.get("required_capabilities")
    if "preferred_worker_codes" in payload:
        legacy_shape["execution"]["preferred_worker_codes"] = payload.get("preferred_worker_codes")
    if "lease_timeout_seconds" in payload:
        legacy_shape["execution"]["lease_timeout_seconds"] = payload.get("lease_timeout_seconds")
    if "goal" in payload:
        legacy_shape["agent_flow"]["goal"] = payload.get("goal")
    if "topic_seed" in payload:
        legacy_shape["agent_flow"]["topic_seed"] = payload.get("topic_seed")
    if "platform_name" in payload:
        legacy_shape["agent_flow"]["platform"] = payload.get("platform_name")
    if "audience" in payload:
        legacy_shape["agent_flow"]["audience"] = payload.get("audience")
    if "tone" in payload:
        legacy_shape["agent_flow"]["tone"] = payload.get("tone")
    if "language" in payload:
        legacy_shape["agent_flow"]["language"] = payload.get("language")
    if "reference_prompt" in payload:
        legacy_shape["agent_flow"]["reference_prompt"] = payload.get("reference_prompt")
    if "reference_copy" in payload:
        legacy_shape["agent_flow"]["reference_copy"] = payload.get("reference_copy")
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
    normalized["execution"]["required_capabilities"] = ensure_str_list(
        normalized["execution"].get("required_capabilities")
    )
    normalized["execution"]["preferred_worker_codes"] = ensure_str_list(
        normalized["execution"].get("preferred_worker_codes")
    )
    normalized["execution"]["lease_timeout_seconds"] = clamp_int(
        normalized["execution"].get("lease_timeout_seconds"),
        get_task_lease_timeout_seconds(),
        60,
        86400,
    )
    normalized["agent_flow"]["goal"] = str(normalized["agent_flow"].get("goal") or "").strip()
    normalized["agent_flow"]["topic_seed"] = str(normalized["agent_flow"].get("topic_seed") or "").strip()
    normalized["agent_flow"]["platform"] = str(normalized["agent_flow"].get("platform") or "tiktok").strip() or "tiktok"
    normalized["agent_flow"]["audience"] = str(normalized["agent_flow"].get("audience") or "").strip()
    normalized["agent_flow"]["tone"] = str(normalized["agent_flow"].get("tone") or "短视频爆款").strip() or "短视频爆款"
    normalized["agent_flow"]["language"] = str(normalized["agent_flow"].get("language") or "zh-CN").strip() or "zh-CN"
    normalized["agent_flow"]["reference_prompt"] = str(
        normalized["agent_flow"].get("reference_prompt") or ""
    ).strip()
    normalized["agent_flow"]["reference_copy"] = str(
        normalized["agent_flow"].get("reference_copy") or ""
    ).strip()
    deepseek_config = normalized["agent_flow"].setdefault("deepseek", {})
    deepseek_config["enabled"] = coerce_bool(deepseek_config.get("enabled"), True)
    deepseek_config["model"] = str(deepseek_config.get("model") or "deepseek-chat").strip() or "deepseek-chat"
    deepseek_config["temperature"] = clamp_float(deepseek_config.get("temperature"), 0.8, 0.0, 2.0)
    deepseek_config["max_topics"] = clamp_int(deepseek_config.get("max_topics"), 5, 1, 20)
    video_config = normalized["agent_flow"].setdefault("video", {})
    video_config["enabled"] = coerce_bool(video_config.get("enabled"), False)
    video_config["provider"] = str(video_config.get("provider") or "agnes").strip() or "agnes"
    video_config["model"] = str(video_config.get("model") or "agnes-video-2.5-flash").strip() or "agnes-video-2.5-flash"
    video_config["seconds"] = str(video_config.get("seconds") or "5").strip() or "5"
    video_config["size"] = str(video_config.get("size") or "1280x720").strip() or "1280x720"
    video_config["poll_timeout_seconds"] = clamp_int(video_config.get("poll_timeout_seconds"), 120, 10, 3600)
    video_config["poll_interval_seconds"] = clamp_int(video_config.get("poll_interval_seconds"), 10, 2, 300)

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
    group_id: Optional[int] = None


class CreateTaskRequest(BaseModel):
    title: str
    task_type: str = "publish"
    source_type: str = "manual"
    source_value: str = ""
    priority: str = "normal"
    group_id: Optional[int] = None
    payload: dict = Field(default_factory=dict)


class WorkerHeartbeatRequest(BaseModel):
    worker_code: str
    display_name: str
    status: str = "idle"
    group_id: Optional[int] = None
    machine_info: str = ""
    capabilities: list[str] = []
    max_parallel_tasks: int = Field(default=1, ge=1, le=8)
    scheduler_weight: int = Field(default=100, ge=1, le=1000)
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


class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=6, max_length=128)
    display_name: str
    role: str = "admin"
    status: str = "active"


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)


class CreateGroupRequest(BaseModel):
    group_name: str
    group_code: str = ""
    owner_user_id: Optional[int] = None
    status: str = "active"
    remark: str = ""
    postforme_api_key: str = ""


class UpdateGroupRequest(BaseModel):
    group_name: Optional[str] = None
    owner_user_id: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    postforme_api_key: Optional[str] = None


class CreateGroupMemberRequest(BaseModel):
    user_id: int
    member_role: str = "editor"


class UpdateGroupMemberRequest(BaseModel):
    member_role: str


class CreateWorkerTokenRequest(BaseModel):
    worker_code: str
    token_name: str = ""
    group_id: Optional[int] = None
    issued_by_user_id: Optional[int] = None
    expire_days: int = Field(default=30, ge=1, le=3650)


class RevokeWorkerTokenRequest(BaseModel):
    reason: str = "manual_revoke"


class LoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=6, max_length=128)


class WorkerRegisterRequest(BaseModel):
    worker_code: str
    display_name: str
    machine_info: str = ""
    capabilities: list[str] = []
    max_parallel_tasks: int = Field(default=1, ge=1, le=8)
    scheduler_weight: int = Field(default=100, ge=1, le=1000)
    heartbeat_note: str = ""


class UpdatePlatformAccountRequest(BaseModel):
    group_id: Optional[int] = None
    account_name: Optional[str] = None
    account_handle: Optional[str] = None
    status: Optional[str] = None


class PostForMeAuthUrlRequest(BaseModel):
    platform: str
    group_id: Optional[int] = None


class PostForMeSyncAccountsRequest(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    group_id: Optional[int] = None


class PostForMeCreatePostRequest(BaseModel):
    social_account_ids: list[str] = Field(default_factory=list)
    caption: str = ""
    media_urls: list[str] = Field(default_factory=list)
    scheduled_at: Optional[str] = None
    group_id: Optional[int] = None


class CreateAgentFlowRunRequest(BaseModel):
    template_id: int
    template_version_id: Optional[int] = None
    group_id: Optional[int] = None
    project_id: Optional[int] = None
    title: str = ""
    run_type: str = "single"
    priority: int = Field(default=100, ge=1, le=999)
    source_mode: str = "manual"
    brief_payload: dict = Field(default_factory=dict)
    platform_targets: list[str] = Field(default_factory=list)


class SelectWorkflowAssetRequest(BaseModel):
    asset_id: int


class UpdateWorkflowAssetRequest(BaseModel):
    title: Optional[str] = None
    content_text: Optional[str] = None
    content_json: Optional[Any] = None


class CreateWorkflowProjectRequest(BaseModel):
    group_id: Optional[int] = None
    project_name: str
    template_id: Optional[int] = None
    platform: str = "tiktok"
    subject_domain: str = ""
    remark: str = ""


class UpdateWorkflowProjectRequest(BaseModel):
    project_name: Optional[str] = None
    template_id: Optional[int] = None
    platform: Optional[str] = None
    subject_domain: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class ApplyWorkflowTemplatePresetRequest(BaseModel):
    preset_type: str
    preset_code: str


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


def get_task_lease_timeout_seconds() -> int:
    raw_value = os.getenv("TASK_LEASE_TIMEOUT_SECONDS", "1800")
    try:
        return max(60, int(raw_value))
    except ValueError:
        return 1800


def build_object_url(key: str) -> str:
    endpoint = get_required_env("S3_ENDPOINT").rstrip("/")
    bucket = get_bucket_name()
    return f"{endpoint}/{bucket}/{key}"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected_digest = password_hash.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return secrets.compare_digest(digest, expected_digest)


def normalize_code(value: str, fallback_prefix: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or f"{fallback_prefix}-{uuid.uuid4().hex[:8]}"


def get_user_session_expire_days() -> int:
    raw_value = os.getenv("USER_SESSION_EXPIRE_DAYS", "7")
    try:
        return max(1, min(30, int(raw_value)))
    except ValueError:
        return 7


def parse_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def is_expired(value: Optional[datetime]) -> bool:
    if not value:
        return False
    current = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return current <= utcnow()


def extract_access_token(authorization: Optional[str], fallback_token: str = "") -> str:
    raw_value = str(authorization or "").strip()
    if raw_value:
        scheme, _, token = raw_value.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
        if not token:
            return raw_value
    return str(fallback_token or "").strip()


def get_web_public_base_url() -> str:
    value = (
        os.getenv("WEB_PUBLIC_BASE_URL")
        or os.getenv("NEXT_PUBLIC_WEB_BASE_URL")
        or "http://localhost:5173"
    )
    return value.rstrip("/")


def get_api_public_base_url(request: Request) -> str:
    configured = os.getenv("API_PUBLIC_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def build_oauth_callback_url(request: Request, platform: str) -> str:
    return f"{get_api_public_base_url(request)}/oauth/{platform}/callback"


def build_accounts_redirect_url(platform: str, status: str, message: str) -> str:
    query = urllib_parse.urlencode(
        {
            "oauth_platform": platform,
            "oauth_status": status,
            "oauth_message": message,
        }
    )
    return f"{get_web_public_base_url()}/accounts?{query}"


def split_scope_string(value: Any) -> list[str]:
    raw_value = str(value or "").replace(",", " ")
    return [item.strip() for item in raw_value.split() if item.strip()]


def get_platform_config(platform: str) -> dict:
    normalized = str(platform or "").strip().lower()
    if normalized not in SUPPORTED_PLATFORM_CODES:
        raise HTTPException(status_code=404, detail="暂不支持当前平台")

    meta_auth_url = f"https://www.facebook.com/{META_GRAPH_API_VERSION}/dialog/oauth"
    meta_token_url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/oauth/access_token"
    configs = {
        "tiktok": {
            "code": "tiktok",
            "label": "TikTok",
            "client_id_env": "TIKTOK_CLIENT_KEY",
            "client_secret_env": "TIKTOK_CLIENT_SECRET",
            "auth_url": "https://www.tiktok.com/v2/auth/authorize/",
            "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
            "profile_mode": "tiktok",
            "default_scopes": ["user.info.basic", "video.list", "video.upload"],
            "scope_separator": ",",
            "authorization_client_param": "client_key",
            "token_client_param": "client_key",
            "requires_client_secret": True,
            "pkce_required": False,
        },
        "youtube": {
            "code": "youtube",
            "label": "YouTube",
            "client_id_env": "YOUTUBE_CLIENT_ID",
            "client_secret_env": "YOUTUBE_CLIENT_SECRET",
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "profile_mode": "youtube",
            "default_scopes": [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/youtube.upload",
            ],
            "scope_separator": " ",
            "authorization_client_param": "client_id",
            "token_client_param": "client_id",
            "requires_client_secret": True,
            "pkce_required": False,
        },
        "facebook": {
            "code": "facebook",
            "label": "Facebook",
            "client_id_env": "FACEBOOK_CLIENT_ID",
            "client_secret_env": "FACEBOOK_CLIENT_SECRET",
            "auth_url": meta_auth_url,
            "token_url": meta_token_url,
            "profile_mode": "facebook",
            "default_scopes": ["pages_show_list", "pages_read_engagement", "pages_manage_posts"],
            "scope_separator": ",",
            "authorization_client_param": "client_id",
            "token_client_param": "client_id",
            "requires_client_secret": True,
            "pkce_required": False,
        },
        "instagram": {
            "code": "instagram",
            "label": "Instagram",
            "client_id_env": "INSTAGRAM_CLIENT_ID",
            "client_secret_env": "INSTAGRAM_CLIENT_SECRET",
            "auth_url": meta_auth_url,
            "token_url": meta_token_url,
            "profile_mode": "instagram",
            "default_scopes": [
                "pages_show_list",
                "pages_read_engagement",
                "instagram_basic",
                "instagram_content_publish",
            ],
            "scope_separator": ",",
            "authorization_client_param": "client_id",
            "token_client_param": "client_id",
            "requires_client_secret": True,
            "pkce_required": False,
        },
        "x": {
            "code": "x",
            "label": "X",
            "client_id_env": "X_CLIENT_ID",
            "client_secret_env": "X_CLIENT_SECRET",
            "auth_url": "https://x.com/i/oauth2/authorize",
            "token_url": "https://api.x.com/2/oauth2/token",
            "profile_mode": "x",
            "default_scopes": ["tweet.read", "tweet.write", "users.read", "offline.access"],
            "scope_separator": " ",
            "authorization_client_param": "client_id",
            "token_client_param": "client_id",
            "requires_client_secret": False,
            "pkce_required": True,
        },
    }

    config = deepcopy(configs[normalized])
    client_id = os.getenv(config["client_id_env"], "").strip()
    client_secret_env = config.get("client_secret_env") or ""
    client_secret = os.getenv(client_secret_env, "").strip() if client_secret_env else ""
    configured_scopes = os.getenv(f"{normalized.upper()}_OAUTH_SCOPES", "").strip()
    scopes = split_scope_string(configured_scopes) or config["default_scopes"]

    config["client_id"] = client_id
    config["client_secret"] = client_secret
    config["scopes"] = scopes
    config["enabled"] = bool(client_id and (client_secret or not config.get("requires_client_secret", False)))
    return config


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def encode_basic_auth(username: str, password: str) -> str:
    raw = f"{username}:{password}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def make_http_request_json(
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    form_data: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> dict:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if form_data is not None:
        body = urllib_parse.urlencode(form_data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib_request.Request(url, data=body, method=method.upper(), headers=request_headers)
    try:
        with urllib_request.urlopen(request, timeout=60) as response:
            raw_body = response.read().decode("utf-8")
            return json.loads(raw_body) if raw_body else {}
    except urllib_error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore")
        try:
            parsed_error = json.loads(error_body) if error_body else {}
        except json.JSONDecodeError:
            parsed_error = {"detail": error_body or str(error)}
        message = (
            parsed_error.get("error_description")
            or parsed_error.get("message")
            or parsed_error.get("detail")
            or error_body
            or str(error)
        )
        raise HTTPException(status_code=400, detail=f"OAuth 请求失败：{message}") from error
    except urllib_error.URLError as error:
        raise HTTPException(status_code=400, detail=f"OAuth 请求失败：{error.reason}") from error


def build_query_url(url: str, params: Optional[dict[str, Any]] = None) -> str:
    if not params:
        return url
    query_string = urllib_parse.urlencode(params, doseq=True)
    return f"{url}{'&' if '?' in url else '?'}{query_string}"


def get_postforme_api_key(raw_value: Optional[str]) -> str:
    api_key = str(raw_value or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="缺少 Post for Me API Key")
    return api_key


def resolve_postforme_api_key(
    db: Session,
    *,
    actor_user: UserAccount,
    requested_group_id: Optional[int],
    header_api_key: Optional[str],
) -> tuple[str, Optional[int]]:
    direct_api_key = str(header_api_key or "").strip()
    if direct_api_key:
        resolved_group_id = None
        if requested_group_id is not None or PUBLIC_BUSINESS_API_MODE:
            resolved_group_id = resolve_effective_group_id(
                db,
                actor_user,
                requested_group_id,
                required_for_non_admin_message="请先选择账号组",
            )
        return direct_api_key, resolved_group_id

    if POST_FOR_ME_DEFAULT_API_KEY:
        resolved_group_id = None
        if requested_group_id is not None or PUBLIC_BUSINESS_API_MODE:
            resolved_group_id = resolve_effective_group_id(
                db,
                actor_user,
                requested_group_id,
                required_for_non_admin_message="请先选择账号组",
            )
        return POST_FOR_ME_DEFAULT_API_KEY, resolved_group_id

    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        requested_group_id,
        required_for_non_admin_message="请先选择已配置 Post for Me API Key 的账号组",
    )
    if effective_group_id is None:
        raise HTTPException(status_code=400, detail="请先选择账号组并配置组级 Post for Me API Key")
    group_record = get_group_or_404(db, effective_group_id)
    api_key = str(group_record.postforme_api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="当前账号组还没有配置 Post for Me API Key")
    return api_key, effective_group_id


def parse_datetime_string(value: Optional[str]) -> Optional[datetime]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def postforme_request_json(
    method: str,
    path: str,
    api_key: str,
    *,
    query_params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> dict:
    url = build_query_url(f"{POST_FOR_ME_BASE_URL}/{path.lstrip('/')}", query_params)
    return make_http_request_json(
        method,
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json_body=json_body,
    )


def extract_avatar_url(profile: dict) -> str:
    return str(
        profile.get("avatar_url")
        or profile.get("profile_image_url")
        or profile.get("profile_picture_url")
        or profile.get("image_url")
        or ""
    )


def normalize_postforme_social_account(item: dict) -> dict:
    profile = item if isinstance(item, dict) else {}
    platform = str(profile.get("platform") or "").strip().lower()
    account_id = str(profile.get("id") or "").strip()
    username = str(profile.get("username") or profile.get("handle") or "").strip()
    name = str(
        profile.get("display_name")
        or profile.get("account_name")
        or profile.get("name")
        or username
        or account_id
    ).strip()
    account_handle = str(profile.get("account_handle") or username or "").strip()
    if account_handle and not account_handle.startswith("@"):
        account_handle = f"@{account_handle}"
    return {
        "platform": platform or "unknown",
        "platform_user_id": account_id,
        "account_name": name or "未命名账号",
        "account_handle": account_handle,
        "profile_url": str(profile.get("profile_url") or profile.get("url") or ""),
        "avatar_url": extract_avatar_url(profile),
        "status": str(profile.get("status") or "active").strip().lower(),
        "token_expires_at": parse_datetime_string(
            profile.get("token_expires_at")
            or profile.get("access_token_expires_at")
            or profile.get("expires_at")
        ),
        "profile": profile,
    }


def sync_postforme_social_accounts(
    db: Session,
    *,
    actor_user: UserAccount,
    api_key: str,
    platforms: list[str],
    group_id: Optional[int],
) -> list[PlatformAccount]:
    query_params: dict[str, Any] = {}
    normalized_platforms = [item for item in ensure_str_list(platforms) if item in SUPPORTED_PLATFORM_CODES]
    if normalized_platforms:
        query_params["platform"] = normalized_platforms
    remote_response = postforme_request_json("GET", "/social-accounts", api_key, query_params=query_params)
    remote_items = remote_response.get("data") if isinstance(remote_response.get("data"), list) else []

    resolved_group_id = None
    if group_id is not None:
        resolved_group_id = resolve_effective_group_id(
            db,
            actor_user,
            group_id,
            required_for_non_admin_message="请先选择要同步到哪个账号组",
        )

    synced_records: list[PlatformAccount] = []
    for item in remote_items:
        normalized = normalize_postforme_social_account(item)
        if not normalized["platform_user_id"]:
            continue
        existing = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.auth_type == "postforme",
                PlatformAccount.platform == normalized["platform"],
                PlatformAccount.platform_user_id == normalized["platform_user_id"],
            )
        )
        record = existing or PlatformAccount(
            platform=normalized["platform"],
            platform_user_id=normalized["platform_user_id"],
            auth_type="postforme",
        )
        if existing is None:
            db.add(record)
        if record.group_id is None and resolved_group_id is not None:
            record.group_id = resolved_group_id
        record.account_name = normalized["account_name"]
        record.account_handle = normalized["account_handle"]
        record.profile_url = normalized["profile_url"]
        record.avatar_url = normalized["avatar_url"]
        record.status = normalized["status"] or record.status or "active"
        record.connected_by_user_id = actor_user.id
        record.token_type = "Bearer"
        record.access_token = ""
        record.refresh_token = ""
        record.token_expires_at = normalized["token_expires_at"]
        record.scope_json = json.dumps([], ensure_ascii=False)
        record.profile_json = json.dumps(normalized["profile"], ensure_ascii=False)
        record.last_synced_at = utcnow()
        synced_records.append(record)
    return synced_records


def get_oauth_provider_cards() -> list[dict]:
    return [
        {
            "code": item["code"],
            "label": item["label"],
            "enabled": item["enabled"],
            "scopes": item["scopes"],
            "pkce_required": item["pkce_required"],
        }
        for item in (get_platform_config(code) for code in SUPPORTED_PLATFORM_CODES)
    ]


def fetch_platform_profile(platform: str, access_token: str) -> dict:
    if platform == "tiktok":
        response = make_http_request_json(
            "GET",
            build_query_url(
                "https://open.tiktokapis.com/v2/user/info/",
                {"fields": "open_id,union_id,avatar_url,display_name,username,profile_deep_link"},
            ),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user = response.get("data", {}).get("user", {})
        username = str(user.get("username") or "").strip()
        return {
            "platform_user_id": str(user.get("open_id") or user.get("union_id") or ""),
            "account_name": str(user.get("display_name") or username or "TikTok Account"),
            "account_handle": f"@{username}" if username else "",
            "profile_url": str(user.get("profile_deep_link") or ""),
            "avatar_url": str(user.get("avatar_url") or ""),
            "profile": user,
        }

    if platform == "youtube":
        user = make_http_request_json(
            "GET",
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        email = str(user.get("email") or "").strip()
        return {
            "platform_user_id": str(user.get("id") or email),
            "account_name": str(user.get("name") or email or "YouTube Account"),
            "account_handle": email,
            "profile_url": "",
            "avatar_url": str(user.get("picture") or ""),
            "profile": user,
        }

    if platform == "facebook":
        user = make_http_request_json(
            "GET",
            build_query_url(
                f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/me",
                {"fields": "id,name,picture.type(large){url}", "access_token": access_token},
            ),
        )
        return {
            "platform_user_id": str(user.get("id") or ""),
            "account_name": str(user.get("name") or "Facebook Account"),
            "account_handle": str(user.get("name") or ""),
            "profile_url": "",
            "avatar_url": str(user.get("picture", {}).get("data", {}).get("url") or ""),
            "profile": user,
        }

    if platform == "instagram":
        page_data = make_http_request_json(
            "GET",
            build_query_url(
                f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/me/accounts",
                {
                    "fields": "id,name,instagram_business_account{id,username,profile_picture_url}",
                    "access_token": access_token,
                },
            ),
        )
        for page in page_data.get("data", []) or []:
            instagram_account = page.get("instagram_business_account") or {}
            if instagram_account.get("id"):
                username = str(instagram_account.get("username") or "").strip()
                return {
                    "platform_user_id": str(instagram_account.get("id") or ""),
                    "account_name": username or str(page.get("name") or "Instagram Account"),
                    "account_handle": f"@{username}" if username else "",
                    "profile_url": f"https://www.instagram.com/{username}/" if username else "",
                    "avatar_url": str(instagram_account.get("profile_picture_url") or ""),
                    "profile": {"page": page, "instagram_business_account": instagram_account},
                }
        raise HTTPException(status_code=400, detail="当前授权下未找到可绑定的 Instagram Business 账号")

    if platform == "x":
        response = make_http_request_json(
            "GET",
            build_query_url(
                "https://api.x.com/2/users/me",
                {"user.fields": "profile_image_url,username,name,verified"},
            ),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user = response.get("data", {})
        username = str(user.get("username") or "").strip()
        return {
            "platform_user_id": str(user.get("id") or ""),
            "account_name": str(user.get("name") or username or "X Account"),
            "account_handle": f"@{username}" if username else "",
            "profile_url": f"https://x.com/{username}" if username else "",
            "avatar_url": str(user.get("profile_image_url") or ""),
            "profile": user,
        }

    raise HTTPException(status_code=400, detail="暂不支持当前平台资料拉取")


def exchange_oauth_code(platform: str, config: dict, code: str, redirect_uri: str, code_verifier: str) -> dict:
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    token_headers = {}

    token_client_param = config.get("token_client_param", "client_id")
    if config.get("client_id"):
        token_payload[token_client_param] = config["client_id"]
    if config.get("client_secret"):
        token_payload["client_secret"] = config["client_secret"]

    if platform == "x":
        token_payload["code_verifier"] = code_verifier
        if config.get("client_secret"):
            token_headers["Authorization"] = f"Basic {encode_basic_auth(config['client_id'], config['client_secret'])}"

    response = make_http_request_json(
        "POST",
        config["token_url"],
        headers=token_headers,
        form_data=token_payload,
    )
    token_data = response.get("data", response)
    expires_in = clamp_int(token_data.get("expires_in"), 0, 0, 315360000)
    refresh_token = str(token_data.get("refresh_token") or "")
    access_token = str(token_data.get("access_token") or "")
    scopes = split_scope_string(token_data.get("scope")) or config["scopes"]
    if not access_token:
        raise HTTPException(status_code=400, detail="OAuth 回调成功，但未返回 access_token")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": str(token_data.get("token_type") or "Bearer"),
        "scopes": scopes,
        "expires_at": utcnow() + timedelta(seconds=expires_in) if expires_in else None,
        "raw_token": token_data,
    }


def create_audit_log(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor_type: str = "system",
    actor_code: str = "",
    actor_user_id: Optional[int] = None,
    detail: Optional[dict] = None,
):
    record = AuditLog(
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        actor_code=actor_code,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
    )
    db.add(record)
    return record


def create_task_execution_record(
    db: Session,
    *,
    task_id: int,
    event_type: str,
    status_before: str,
    status_after: str,
    group_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    worker_code: str = "",
    worker_token_id: Optional[int] = None,
    attempt_count: int = 0,
    retry_count: int = 0,
    error_message: str = "",
    detail: Optional[dict] = None,
):
    record = TaskExecutionRecord(
        task_id=task_id,
        group_id=group_id,
        actor_user_id=actor_user_id,
        worker_code=worker_code,
        worker_token_id=worker_token_id,
        event_type=event_type,
        status_before=status_before,
        status_after=status_after,
        attempt_count=attempt_count,
        retry_count=retry_count,
        error_message=error_message,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
    )
    db.add(record)
    return record


def create_asset_record(
    db: Session,
    *,
    source_type: str,
    group_id: Optional[int],
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
        group_id=group_id,
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
        group_id=task.group_id,
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
        "group_id": record.group_id,
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


def get_task_required_capabilities(record: TaskRecord) -> list[str]:
    payload = normalize_task_payload(load_json_field(record.payload_json, {}))
    return ensure_str_list(payload.get("execution", {}).get("required_capabilities"))


def get_task_preferred_worker_codes(record: TaskRecord) -> list[str]:
    payload = normalize_task_payload(load_json_field(record.payload_json, {}))
    return ensure_str_list(payload.get("execution", {}).get("preferred_worker_codes"))


def get_task_lease_timeout(record: TaskRecord) -> int:
    payload = normalize_task_payload(load_json_field(record.payload_json, {}))
    return clamp_int(
        payload.get("execution", {}).get("lease_timeout_seconds"),
        get_task_lease_timeout_seconds(),
        60,
        86400,
    )


def get_worker_capabilities(record: WorkerNode) -> list[str]:
    return ensure_str_list(load_json_field(record.capabilities, []))


def count_worker_running_tasks(db: Session, worker_code: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TaskRecord)
        .where(TaskRecord.assigned_worker_code == worker_code, TaskRecord.status == "running")
    ) or 0


def get_worker_available_slots(db: Session, record: WorkerNode) -> int:
    running_count = count_worker_running_tasks(db, record.worker_code)
    return max(0, int(record.max_parallel_tasks or 1) - running_count)


def worker_can_claim_task(worker: WorkerNode, task: TaskRecord) -> tuple[bool, str]:
    required_capabilities = set(get_task_required_capabilities(task))
    worker_capabilities = set(get_worker_capabilities(worker))
    missing_capabilities = sorted(required_capabilities - worker_capabilities)
    if missing_capabilities:
        return False, f"缺少能力：{', '.join(missing_capabilities)}"

    preferred_worker_codes = get_task_preferred_worker_codes(task)
    if preferred_worker_codes and worker.worker_code not in preferred_worker_codes:
        return False, "当前任务已绑定其他 Worker"

    if task.assigned_worker_code and task.assigned_worker_code != worker.worker_code:
        return False, "当前任务已分配给其他 Worker"

    return True, ""


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
        "group_id": record.group_id,
        "created_by_user_id": record.created_by_user_id,
        "triggered_by_user_id": record.triggered_by_user_id,
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


def get_default_agent_flow_brief_schema() -> dict:
    return {
        "fields": [
            {"key": "goal", "label": "任务目标", "type": "text", "required": True},
            {"key": "topic_seed", "label": "选题方向", "type": "textarea", "required": True},
            {"key": "platform", "label": "目标平台", "type": "select", "options": ["tiktok", "youtube", "xiaohongshu"]},
            {"key": "audience", "label": "目标人群", "type": "text"},
            {"key": "tone", "label": "文案风格", "type": "text"},
            {"key": "language", "label": "语言", "type": "text"},
            {"key": "reference_prompt", "label": "参考提示词", "type": "textarea"},
            {"key": "reference_copy", "label": "参考文案", "type": "textarea"},
            {"key": "max_topics", "label": "候选选题数", "type": "number"},
            {"key": "video_enabled", "label": "生成视频提示词", "type": "boolean"},
        ]
    }


def get_default_agent_flow_stage_schema() -> list[dict]:
    return [
        {"code": "brief_collect", "name": "任务 Brief", "required_capability": "editor"},
        {"code": "topic_generate", "name": "选题池", "required_capability": "llm-agent"},
        {"code": "script_generate", "name": "脚本", "required_capability": "llm-agent"},
        {"code": "storyboard_generate", "name": "分镜", "required_capability": "llm-agent"},
        {"code": "prompt_expand", "name": "提示词", "required_capability": "llm-agent"},
        {"code": "generate_assets", "name": "生成资产", "required_capability": "video-gen"},
        {"code": "publish_copy_generate", "name": "发布稿", "required_capability": "llm-agent"},
    ]


def get_default_agent_flow_model_config() -> dict:
    return {
        "deepseek": {
            "enabled": True,
            "model": "deepseek-chat",
            "temperature": 0.8,
            "max_topics": 5,
        },
        "video": {
            "enabled": False,
            "provider": "agnes",
            "model": "agnes-video-2.5-flash",
            "seconds": "5",
            "size": "1280x720",
            "poll_timeout_seconds": 120,
            "poll_interval_seconds": 10,
        },
    }


def get_default_agent_flow_style_bibles() -> list[dict]:
    return [
        {
            "code": "hook_contrast",
            "name": "高点击反差口播",
            "summary": "强钩子、强反差、适合短视频起号",
            "tone": "高点击、强反差、节奏快",
            "keywords": ["先抛结果", "冲突对比", "压缩废话", "结尾留钩子"],
            "opening_patterns": ["很多人以为...", "别再直接...", "你以为...其实..."],
        },
        {
            "code": "coach_practical",
            "name": "陪跑实战派",
            "summary": "像运营顾问在旁边拆步骤，适合转化和留资",
            "tone": "直给、具体、像在带做",
            "keywords": ["少空话", "给步骤", "强调执行门槛", "避免玄学表达"],
            "opening_patterns": ["我直接把流程给你", "先别急着做全套", "你先把这一步跑通"],
        },
        {
            "code": "authority_explainer",
            "name": "权威解释型",
            "summary": "适合知识型账号，重结论和框架感",
            "tone": "稳、清楚、结论先行",
            "keywords": ["一句话定结论", "框架拆解", "少情绪词", "强调判断标准"],
            "opening_patterns": ["先说结论", "这个问题核心就两点", "很多账号卡在这里"],
        },
    ]


def get_default_agent_flow_character_bibles() -> list[dict]:
    return [
        {
            "code": "ai_operator",
            "name": "AI运营操盘手",
            "summary": "擅长把复杂工作流拆成可执行动作",
            "persona": {
                "identity": "有实操经验的内容操盘手",
                "traits": ["结果导向", "不说空话", "先闭环后扩展"],
                "speaking_style": "像在带团队落地，不绕弯",
            },
        },
        {
            "code": "newbie_coach",
            "name": "新手陪跑教练",
            "summary": "适合低门槛转化和教程向内容",
            "persona": {
                "identity": "懂新手痛点的陪跑教练",
                "traits": ["耐心", "鼓励", "拆解细"],
                "speaking_style": "一步一步说清楚，降低焦虑",
            },
        },
        {
            "code": "growth_analyst",
            "name": "增长分析师",
            "summary": "适合做数据、策略和案例拆解",
            "persona": {
                "identity": "偏策略与数据判断的增长分析师",
                "traits": ["克制", "重证据", "重结构"],
                "speaking_style": "先结论再论证，适度引用指标",
            },
        },
    ]


def get_default_agent_flow_shot_bibles() -> list[dict]:
    return [
        {
            "code": "fast_hook",
            "name": "快节奏钩子型",
            "summary": "3-5 秒一个信息点，适合短视频口播",
            "rules": {"rhythm": "3-5 秒一个信息点", "camera": "中近景为主", "visuals": ["关键词大字卡", "对比截图", "步骤编号"]},
        },
        {
            "code": "case_breakdown",
            "name": "案例拆解型",
            "summary": "先结果，再拆过程，适合教程和复盘",
            "rules": {"rhythm": "8-12 秒一个章节", "camera": "口播 + 屏录切换", "visuals": ["案例前后对比", "表格", "流程图"]},
        },
        {
            "code": "story_drive",
            "name": "故事推进型",
            "summary": "适合人物、经历、项目推进类内容",
            "rules": {"rhythm": "冲突点驱动转场", "camera": "情绪特写 + 插叙素材", "visuals": ["时间线", "关键节点字幕"]},
        },
    ]


def get_default_agent_flow_model_presets() -> list[dict]:
    return [
        {
            "code": "balanced_default",
            "name": "平衡默认",
            "summary": "优先保证稳定和速度，适合日常量产",
            "config": get_default_agent_flow_model_config(),
        },
        {
            "code": "fast_copy",
            "name": "极速文案",
            "summary": "关闭视频生成，先把选题和发布稿跑快",
            "config": {
                "deepseek": {"enabled": True, "model": "deepseek-chat", "temperature": 0.7, "max_topics": 8},
                "video": {"enabled": False, "provider": "agnes", "model": "agnes-video-2.5-flash", "seconds": "5", "size": "1280x720"},
            },
        },
        {
            "code": "media_heavy",
            "name": "重媒体产出",
            "summary": "保留视频生成，适合最终成片前的完整链路",
            "config": {
                "deepseek": {"enabled": True, "model": "deepseek-chat", "temperature": 0.85, "max_topics": 5},
                "video": {
                    "enabled": True,
                    "provider": "agnes",
                    "model": "agnes-video-2.5-flash",
                    "seconds": "5",
                    "size": "1280x720",
                    "poll_timeout_seconds": 180,
                    "poll_interval_seconds": 10,
                },
            },
        },
    ]


def get_default_agent_flow_stage_chain_presets() -> list[dict]:
    return [
        {
            "code": "full_chain",
            "name": "完整链路",
            "summary": "Brief -> 选题 -> 脚本 -> 分镜 -> 提示词 -> 资产 -> 发布稿",
            "stage_schema": get_default_agent_flow_stage_schema(),
        },
        {
            "code": "copy_only",
            "name": "纯文案链",
            "summary": "不走视频生成，只保留文案核心阶段",
            "stage_schema": [
                {"code": "brief_collect", "name": "任务 Brief", "required_capability": "editor"},
                {"code": "topic_generate", "name": "选题池", "required_capability": "llm-agent"},
                {"code": "script_generate", "name": "脚本", "required_capability": "llm-agent"},
                {"code": "prompt_expand", "name": "提示词", "required_capability": "llm-agent"},
                {"code": "publish_copy_generate", "name": "发布稿", "required_capability": "llm-agent"},
            ],
        },
        {
            "code": "media_first",
            "name": "媒体优先链",
            "summary": "更强调分镜和生成资产，适合成片导向",
            "stage_schema": [
                {"code": "brief_collect", "name": "任务 Brief", "required_capability": "editor"},
                {"code": "topic_generate", "name": "选题池", "required_capability": "llm-agent"},
                {"code": "storyboard_generate", "name": "分镜", "required_capability": "llm-agent"},
                {"code": "prompt_expand", "name": "提示词", "required_capability": "llm-agent"},
                {"code": "generate_assets", "name": "生成资产", "required_capability": "video-gen"},
                {"code": "publish_copy_generate", "name": "发布稿", "required_capability": "llm-agent"},
            ],
        },
    ]


def get_default_agent_flow_platform_presets() -> list[dict]:
    return [
        {"code": "tiktok", "name": "TikTok", "summary": "强钩子、快节奏、强转场", "recommended_style": "hook_contrast"},
        {"code": "youtube", "name": "YouTube Shorts", "summary": "信息密度高，前 3 秒要交代主题", "recommended_style": "authority_explainer"},
        {"code": "xiaohongshu", "name": "小红书", "summary": "更生活化和经验分享感", "recommended_style": "coach_practical"},
    ]


def get_agent_flow_settings_catalog() -> dict:
    return {
        "style_bibles": get_default_agent_flow_style_bibles(),
        "character_bibles": get_default_agent_flow_character_bibles(),
        "shot_bibles": get_default_agent_flow_shot_bibles(),
        "model_presets": get_default_agent_flow_model_presets(),
        "stage_chain_presets": get_default_agent_flow_stage_chain_presets(),
        "platform_presets": get_default_agent_flow_platform_presets(),
    }


def find_agent_flow_preset(preset_type: str, preset_code: str) -> Optional[dict]:
    catalog = get_agent_flow_settings_catalog()
    items = catalog.get(preset_type)
    if not isinstance(items, list):
        return None
    normalized_code = str(preset_code or "").strip()
    for item in items:
        if str(item.get("code") or "").strip() == normalized_code:
            return item
    return None


def ensure_default_agent_flow_template(db: Session) -> tuple[WorkflowTemplate, WorkflowTemplateVersion]:
    template = db.scalar(
        select(WorkflowTemplate).where(WorkflowTemplate.template_code == "short-video-general")
    )
    if template:
        version = db.scalar(
            select(WorkflowTemplateVersion).where(
                WorkflowTemplateVersion.id == template.current_version_id
            )
        )
        if version:
            return template, version

    template = template or WorkflowTemplate(
        group_id=ensure_public_test_group(db).id if PUBLIC_BUSINESS_API_MODE else None,
        template_code="short-video-general",
        template_name="通用短视频文案工作流",
        category="short_video",
        platform_scope_json=json.dumps(["tiktok", "youtube"], ensure_ascii=False),
        style_type="高点击口播",
        status="active",
        remark="默认内置模板，先承接 agent_flow 最小闭环",
        created_by_user_id=get_public_business_actor(db).id if PUBLIC_BUSINESS_API_MODE else None,
    )
    if template.id is None:
        db.add(template)
        db.flush()

    version = WorkflowTemplateVersion(
        template_id=template.id,
        version_no=1,
        version_name="v1 默认版",
        brief_schema_json=json.dumps(get_default_agent_flow_brief_schema(), ensure_ascii=False),
        stage_schema_json=json.dumps(get_default_agent_flow_stage_schema(), ensure_ascii=False),
        prompt_blocks_json=json.dumps(
            {
                "role": "短视频策划与文案专家",
                "goal": "输出可直接进入发布中心的选题、提示词和发布文案",
                "constraints": ["输出紧凑", "强调钩子", "优先适配短视频平台"],
            },
            ensure_ascii=False,
        ),
        style_bible_json=json.dumps({"tone": "高点击、强反差、适合短视频口播"}, ensure_ascii=False),
        shot_bible_json=json.dumps({"rhythm": "3-5 秒一个信息点"}, ensure_ascii=False),
        default_model_config_json=json.dumps(get_default_agent_flow_model_config(), ensure_ascii=False),
        output_schema_json=json.dumps(
            {
                "assets": ["topic_candidates", "script", "video_prompt", "publish_copy", "video_output"]
            },
            ensure_ascii=False,
        ),
        is_published=True,
        created_by_user_id=get_public_business_actor(db).id if PUBLIC_BUSINESS_API_MODE else None,
    )
    db.add(version)
    db.flush()
    template.current_version_id = version.id
    return template, version


def get_workflow_template_or_404(db: Session, template_id: int) -> WorkflowTemplate:
    record = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.id == template_id))
    if not record:
        raise HTTPException(status_code=404, detail="工作流模板不存在")
    return record


def get_workflow_template_version_or_404(db: Session, version_id: int) -> WorkflowTemplateVersion:
    record = db.scalar(select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id == version_id))
    if not record:
        raise HTTPException(status_code=404, detail="工作流模板版本不存在")
    return record


def get_workflow_run_or_404(db: Session, run_id: int) -> WorkflowRun:
    record = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
    if not record:
        raise HTTPException(status_code=404, detail="工作流运行不存在")
    return record


def get_workflow_bundle_or_404(db: Session, bundle_id: int) -> WorkflowAssetBundle:
    record = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.id == bundle_id))
    if not record:
        raise HTTPException(status_code=404, detail="资产包不存在")
    return record


def get_workflow_asset_or_404(db: Session, asset_id: int) -> WorkflowAsset:
    record = db.scalar(select(WorkflowAsset).where(WorkflowAsset.id == asset_id))
    if not record:
        raise HTTPException(status_code=404, detail="资产不存在")
    return record


def get_workflow_project_or_404(db: Session, project_id: int) -> WorkflowProject:
    record = db.scalar(select(WorkflowProject).where(WorkflowProject.id == project_id))
    if not record:
        raise HTTPException(status_code=404, detail="项目不存在")
    return record


def get_workflow_stage_or_404(db: Session, stage_id: int) -> WorkflowRunStage:
    record = db.scalar(select(WorkflowRunStage).where(WorkflowRunStage.id == stage_id))
    if not record:
        raise HTTPException(status_code=404, detail="阶段记录不存在")
    return record


def serialize_workflow_template_version(record: WorkflowTemplateVersion) -> dict:
    return {
        "id": record.id,
        "template_id": record.template_id,
        "version_no": record.version_no,
        "version_name": record.version_name,
        "brief_schema": load_json_field(record.brief_schema_json, {}),
        "stage_schema": load_json_field(record.stage_schema_json, []),
        "prompt_blocks": load_json_field(record.prompt_blocks_json, {}),
        "style_bible": load_json_field(record.style_bible_json, {}),
        "shot_bible": load_json_field(record.shot_bible_json, {}),
        "default_model_config": load_json_field(record.default_model_config_json, {}),
        "output_schema": load_json_field(record.output_schema_json, {}),
        "is_published": bool(record.is_published),
        "created_by_user_id": record.created_by_user_id,
        "created_at": parse_datetime(record.created_at),
    }


def serialize_workflow_template(record: WorkflowTemplate, version: Optional[WorkflowTemplateVersion]) -> dict:
    return {
        "id": record.id,
        "group_id": record.group_id,
        "template_code": record.template_code,
        "template_name": record.template_name,
        "category": record.category,
        "platform_scope": load_json_field(record.platform_scope_json, []),
        "style_type": record.style_type,
        "status": record.status,
        "current_version_id": record.current_version_id,
        "remark": record.remark,
        "created_by_user_id": record.created_by_user_id,
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
        "current_version": serialize_workflow_template_version(version) if version else None,
    }


def serialize_workflow_stage(record: WorkflowRunStage) -> dict:
    return {
        "id": record.id,
        "run_id": record.run_id,
        "stage_code": record.stage_code,
        "stage_name": record.stage_name,
        "stage_order": record.stage_order,
        "worker_code": record.worker_code,
        "required_capability": record.required_capability,
        "input_payload": load_json_field(record.input_payload_json, {}),
        "output_payload": load_json_field(record.output_payload_json, {}),
        "status": record.status,
        "retry_count": record.retry_count,
        "error_message": record.error_message,
        "started_at": parse_datetime(record.started_at),
        "finished_at": parse_datetime(record.finished_at),
        "created_at": parse_datetime(record.created_at),
    }


def serialize_workflow_asset(record: WorkflowAsset) -> dict:
    return {
        "id": record.id,
        "group_id": record.group_id,
        "bundle_id": record.bundle_id,
        "run_stage_id": record.run_stage_id,
        "asset_type": record.asset_type,
        "asset_role": record.asset_role,
        "title": record.title,
        "content_text": record.content_text,
        "content_json": load_json_field(record.content_json, {}),
        "file_asset_id": record.file_asset_id,
        "r2_key": record.r2_key,
        "mime_type": record.mime_type,
        "sort_order": record.sort_order,
        "version_no": record.version_no,
        "is_selected": bool(record.is_selected),
        "created_at": parse_datetime(record.created_at),
    }


def serialize_workflow_bundle(record: WorkflowAssetBundle) -> dict:
    return {
        "id": record.id,
        "group_id": record.group_id,
        "run_id": record.run_id,
        "bundle_code": record.bundle_code,
        "bundle_name": record.bundle_name,
        "content_type": record.content_type,
        "primary_platform": record.primary_platform,
        "status": record.status,
        "summary": record.summary,
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
    }


def serialize_workflow_publish_link(record: WorkflowPublishLink) -> dict:
    return {
        "id": record.id,
        "group_id": record.group_id,
        "bundle_id": record.bundle_id,
        "publish_draft_id": record.publish_draft_id,
        "platform": record.platform,
        "title_text": record.title_text,
        "body_text": record.body_text,
        "cover_asset_id": record.cover_asset_id,
        "video_asset_id": record.video_asset_id,
        "status": record.status,
        "pushed_at": parse_datetime(record.pushed_at),
        "created_at": parse_datetime(record.created_at),
    }


def serialize_workflow_project(record: WorkflowProject, *, template: Optional[WorkflowTemplate] = None) -> dict:
    return {
        "id": record.id,
        "group_id": record.group_id,
        "project_code": record.project_code,
        "project_name": record.project_name,
        "template_id": record.template_id,
        "platform": record.platform,
        "subject_domain": record.subject_domain,
        "status": record.status,
        "owner_user_id": record.owner_user_id,
        "remark": record.remark,
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
        "template": serialize_workflow_template(template, None) if template else None,
    }


def serialize_workflow_run(
    record: WorkflowRun,
    *,
    template: Optional[WorkflowTemplate] = None,
    template_version: Optional[WorkflowTemplateVersion] = None,
    bundle: Optional[WorkflowAssetBundle] = None,
    task: Optional[TaskRecord] = None,
) -> dict:
    return {
        "id": record.id,
        "group_id": record.group_id,
        "project_id": record.project_id,
        "template_id": record.template_id,
        "template_version_id": record.template_version_id,
        "task_record_id": record.task_record_id,
        "run_code": record.run_code,
        "run_type": record.run_type,
        "title": record.title,
        "brief_payload": load_json_field(record.brief_payload_json, {}),
        "platform_targets": load_json_field(record.platform_targets_json, []),
        "status": record.status,
        "current_stage_code": record.current_stage_code,
        "priority": record.priority,
        "source_mode": record.source_mode,
        "created_by_user_id": record.created_by_user_id,
        "triggered_by_user_id": record.triggered_by_user_id,
        "started_at": parse_datetime(record.started_at),
        "finished_at": parse_datetime(record.finished_at),
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
        "template": serialize_workflow_template(template, template_version) if template else None,
        "task": serialize_task_record(task) if task else None,
        "bundle": serialize_workflow_bundle(bundle) if bundle else None,
    }


def save_workflow_stage_payloads(record: WorkflowRunStage, input_payload: dict, output_payload: dict) -> bool:
    next_input_json = json.dumps(input_payload or {}, ensure_ascii=False)
    next_output_json = json.dumps(output_payload or {}, ensure_ascii=False)
    changed = False
    if record.input_payload_json != next_input_json:
        record.input_payload_json = next_input_json
        changed = True
    if record.output_payload_json != next_output_json:
        record.output_payload_json = next_output_json
        changed = True
    return changed


def build_agent_flow_task_payload_from_template(
    version: WorkflowTemplateVersion,
    brief_payload: dict,
    platform_targets: list[str],
) -> dict:
    normalized_platforms = ensure_str_list(platform_targets)
    model_config = load_json_field(version.default_model_config_json, {})
    deepseek_config = model_config.get("deepseek") if isinstance(model_config.get("deepseek"), dict) else {}
    video_config = model_config.get("video") if isinstance(model_config.get("video"), dict) else {}
    topic_seed = str(brief_payload.get("topic_seed") or "").strip()
    platform = str(
        brief_payload.get("platform")
        or (normalized_platforms[0] if normalized_platforms else "tiktok")
        or "tiktok"
    ).strip()
    payload = build_task_payload_defaults("balanced")
    payload["publish"]["platforms"] = normalized_platforms or [platform]
    payload["output"]["prefix"] = "agent-flow"
    payload["execution"]["required_capabilities"] = ["llm-agent"]
    payload["agent_flow"]["goal"] = str(
        brief_payload.get("goal") or "选题/提示词优化/发布文案生成"
    ).strip()
    payload["agent_flow"]["topic_seed"] = topic_seed
    payload["agent_flow"]["platform"] = platform or "tiktok"
    payload["agent_flow"]["audience"] = str(brief_payload.get("audience") or "").strip()
    payload["agent_flow"]["tone"] = str(brief_payload.get("tone") or "高点击、强反差、适合短视频口播").strip()
    payload["agent_flow"]["language"] = str(brief_payload.get("language") or "zh-CN").strip()
    payload["agent_flow"]["reference_prompt"] = str(brief_payload.get("reference_prompt") or "").strip()
    payload["agent_flow"]["reference_copy"] = str(brief_payload.get("reference_copy") or "").strip()
    payload["agent_flow"]["deepseek"]["enabled"] = coerce_bool(deepseek_config.get("enabled"), True)
    payload["agent_flow"]["deepseek"]["model"] = str(deepseek_config.get("model") or "deepseek-chat").strip()
    payload["agent_flow"]["deepseek"]["temperature"] = clamp_float(
        brief_payload.get("temperature", deepseek_config.get("temperature")),
        0.8,
        0.0,
        2.0,
    )
    payload["agent_flow"]["deepseek"]["max_topics"] = clamp_int(
        brief_payload.get("max_topics", deepseek_config.get("max_topics")),
        5,
        1,
        20,
    )
    payload["agent_flow"]["video"]["enabled"] = coerce_bool(
        brief_payload.get("video_enabled", video_config.get("enabled")),
        False,
    )
    payload["agent_flow"]["video"]["provider"] = str(video_config.get("provider") or "agnes").strip() or "agnes"
    payload["agent_flow"]["video"]["model"] = str(
        video_config.get("model") or "agnes-video-2.5-flash"
    ).strip() or "agnes-video-2.5-flash"
    payload["agent_flow"]["video"]["seconds"] = str(video_config.get("seconds") or "5").strip() or "5"
    payload["agent_flow"]["video"]["size"] = str(video_config.get("size") or "1280x720").strip() or "1280x720"
    payload["agent_flow"]["video"]["poll_timeout_seconds"] = clamp_int(
        video_config.get("poll_timeout_seconds"),
        120,
        10,
        3600,
    )
    payload["agent_flow"]["video"]["poll_interval_seconds"] = clamp_int(
        video_config.get("poll_interval_seconds"),
        10,
        2,
        300,
    )
    return normalize_task_payload(payload)


def upsert_workflow_asset(
    db: Session,
    *,
    bundle: WorkflowAssetBundle,
    run_stage_id: Optional[int],
    asset_type: str,
    title: str,
    content_text: str = "",
    content_json: Optional[dict | list] = None,
    mime_type: str = "",
    r2_key: str = "",
    sort_order: int = 0,
):
    existing = db.scalar(
        select(WorkflowAsset).where(
            WorkflowAsset.bundle_id == bundle.id,
            WorkflowAsset.asset_type == asset_type,
            WorkflowAsset.sort_order == sort_order,
        )
    )
    record = existing or WorkflowAsset(
        group_id=bundle.group_id,
        bundle_id=bundle.id,
        run_stage_id=run_stage_id,
        asset_type=asset_type,
        asset_role="primary",
        title=title,
        sort_order=sort_order,
        version_no=1,
        is_selected=True,
    )
    if existing is None:
        db.add(record)
    record.run_stage_id = run_stage_id
    record.title = title
    record.content_text = content_text
    record.content_json = json.dumps(content_json or {}, ensure_ascii=False)
    record.mime_type = mime_type
    record.r2_key = r2_key
    return record


def sync_workflow_run_state(db: Session, run: WorkflowRun) -> bool:
    changed = False
    task = db.scalar(select(TaskRecord).where(TaskRecord.id == run.task_record_id)) if run.task_record_id else None
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == run.id))
    stages = db.scalars(
        select(WorkflowRunStage).where(WorkflowRunStage.run_id == run.id).order_by(WorkflowRunStage.stage_order)
    ).all()
    stage_by_code = {item.stage_code: item for item in stages}
    task_state = get_task_runtime_state(task) if task else {}
    brief_payload = load_json_field(run.brief_payload_json, {})
    task_payload = normalize_task_payload(load_json_field(task.payload_json, {})) if task else build_task_payload_defaults("balanced")
    output = task_state.get("output") if isinstance(task_state.get("output"), dict) else {}
    agent_flow_output = output.get("agent_flow") if isinstance(output.get("agent_flow"), dict) else {}
    deepseek_output = agent_flow_output.get("deepseek") if isinstance(agent_flow_output.get("deepseek"), dict) else {}
    video_output = agent_flow_output.get("video") if isinstance(agent_flow_output.get("video"), dict) else {}
    topic_input_payload = {
        "goal": str(brief_payload.get("goal") or task_payload["agent_flow"]["goal"] or "").strip(),
        "topic_seed": str(brief_payload.get("topic_seed") or task_payload["agent_flow"]["topic_seed"] or "").strip(),
        "platform": str(brief_payload.get("platform") or task_payload["agent_flow"]["platform"] or "").strip(),
        "audience": str(brief_payload.get("audience") or task_payload["agent_flow"]["audience"] or "").strip(),
        "tone": str(brief_payload.get("tone") or task_payload["agent_flow"]["tone"] or "").strip(),
        "language": str(brief_payload.get("language") or task_payload["agent_flow"]["language"] or "").strip(),
        "reference_prompt": str(brief_payload.get("reference_prompt") or task_payload["agent_flow"]["reference_prompt"] or "").strip(),
        "reference_copy": str(brief_payload.get("reference_copy") or task_payload["agent_flow"]["reference_copy"] or "").strip(),
        "max_topics": int(task_payload["agent_flow"]["deepseek"]["max_topics"] or 5),
        "video_enabled": bool(task_payload["agent_flow"]["video"]["enabled"]),
    }
    topic_output_payload = {
        "selected_topic": str(deepseek_output.get("selected_topic") or "").strip(),
        "topic_candidates": deepseek_output.get("topic_candidates") or deepseek_output.get("topics") or [],
    }
    optimized_prompt = str(deepseek_output.get("optimized_prompt") or "").strip()
    video_prompt = str(deepseek_output.get("video_prompt") or "").strip()
    publish_copy_output = deepseek_output.get("publish_copy") if isinstance(deepseek_output.get("publish_copy"), dict) else {}
    stage_payload_map = {
        "brief_collect": {
            "input": brief_payload,
            "output": topic_input_payload,
        },
        "topic_generate": {
            "input": topic_input_payload,
            "output": topic_output_payload,
        },
        "script_generate": {
            "input": {
                "selected_topic": topic_output_payload["selected_topic"],
                "audience": topic_input_payload["audience"],
                "tone": topic_input_payload["tone"],
                "reference_copy": topic_input_payload["reference_copy"],
            },
            "output": {
                "optimized_prompt": optimized_prompt,
                "note": "当前执行链暂以优化提示词承接脚本生成结果",
            },
        },
        "storyboard_generate": {
            "input": {
                "selected_topic": topic_output_payload["selected_topic"],
                "optimized_prompt": optimized_prompt,
            },
            "output": {
                "note": "当前执行链暂未拆分独立分镜输出，后续可在 Worker 侧补齐",
            },
        },
        "prompt_expand": {
            "input": {
                "selected_topic": topic_output_payload["selected_topic"],
                "optimized_prompt": optimized_prompt,
                "reference_prompt": topic_input_payload["reference_prompt"],
            },
            "output": {
                "optimized_prompt": optimized_prompt,
                "video_prompt": video_prompt,
            },
        },
        "generate_assets": {
            "input": {
                "video_enabled": bool(task_payload["agent_flow"]["video"]["enabled"]),
                "video_prompt": video_prompt,
                "provider": task_payload["agent_flow"]["video"]["provider"],
                "model": task_payload["agent_flow"]["video"]["model"],
            },
            "output": video_output if isinstance(video_output, dict) else {},
        },
        "publish_copy_generate": {
            "input": {
                "selected_topic": topic_output_payload["selected_topic"],
                "optimized_prompt": optimized_prompt,
                "platforms": task_payload["publish"]["platforms"],
            },
            "output": publish_copy_output,
        },
    }

    if task and run.status != task.status:
        run.status = task.status
        changed = True
    previous_current_stage_code = run.current_stage_code
    if task and task.status in {"pending", "queued", "running"}:
        run.current_stage_code = run.current_stage_code or "topic_generate"
    elif task and task.status == "success":
        run.current_stage_code = "publish_copy_generate"
    if previous_current_stage_code != run.current_stage_code:
        changed = True
    if task and task.status == "running" and run.started_at is None:
        run.started_at = task.updated_at or utcnow()
        changed = True
    if task and task.status in {"success", "failed", "cancelled"}:
        finished_at = task.updated_at or utcnow()
        if run.finished_at != finished_at:
            run.finished_at = finished_at
            changed = True

    active_stage_code = run.current_stage_code or "topic_generate"
    active_stage = stage_by_code.get(active_stage_code)
    active_stage_order = active_stage.stage_order if active_stage else 2
    for stage in stages:
        previous_status = stage.status
        previous_worker_code = stage.worker_code
        previous_error = stage.error_message
        stage_payloads = stage_payload_map.get(stage.stage_code, {"input": {}, "output": {}})
        if stage.stage_code == "brief_collect":
            stage.status = "success"
            stage.finished_at = stage.finished_at or run.created_at or utcnow()
        elif not task:
            stage.status = "pending"
        elif task.status in {"pending", "queued"}:
            if stage.stage_order < active_stage_order:
                stage.status = "success"
            elif stage.stage_order == active_stage_order:
                stage.status = "queued"
            else:
                stage.status = "pending"
        elif task.status == "running":
            if stage.stage_order < active_stage_order:
                stage.status = "success"
            elif stage.stage_order == active_stage_order:
                stage.status = "running"
                stage.started_at = stage.started_at or utcnow()
                stage.worker_code = task.assigned_worker_code or ""
            else:
                stage.status = "pending"
        elif task.status == "success":
            stage.status = "success"
            stage.started_at = stage.started_at or task.created_at or utcnow()
            stage.finished_at = task.updated_at or utcnow()
            stage.worker_code = task.assigned_worker_code or stage.worker_code
        else:
            if stage.stage_order < active_stage_order:
                stage.status = "success"
            elif stage.stage_order == active_stage_order:
                stage.status = "failed"
                stage.error_message = str(task_state.get("last_error") or "")
                stage.worker_code = task.assigned_worker_code or ""
                stage.finished_at = task.updated_at or utcnow()
            else:
                stage.status = "pending"
        if task and task.status == "failed" and stage.stage_code == "topic_generate":
            stage_payloads = {
                "input": stage_payloads.get("input") or {},
                "output": {"last_error": str(task_state.get("last_error") or "")},
            }
        if save_workflow_stage_payloads(stage, stage_payloads.get("input") or {}, stage_payloads.get("output") or {}):
            changed = True
        if previous_status != stage.status or previous_worker_code != stage.worker_code or previous_error != stage.error_message:
            changed = True

    if bundle:
        next_bundle_status = "ready" if task and task.status == "success" else "draft"
        if bundle.status != next_bundle_status:
            bundle.status = next_bundle_status
            changed = True
        summary = str(deepseek_output.get("selected_topic") or deepseek_output.get("optimized_prompt") or "").strip()
        if summary and bundle.summary != summary:
            bundle.summary = summary
            changed = True

    if bundle and task and task.status == "success":
        topic_stage_id = stage_by_code.get("topic_generate").id if stage_by_code.get("topic_generate") else None
        prompt_stage_id = stage_by_code.get("prompt_expand").id if stage_by_code.get("prompt_expand") else None
        publish_stage_id = stage_by_code.get("publish_copy_generate").id if stage_by_code.get("publish_copy_generate") else None
        asset_stage_id = stage_by_code.get("generate_assets").id if stage_by_code.get("generate_assets") else None
        topic_candidates = deepseek_output.get("topic_candidates") or deepseek_output.get("topics") or []
        upsert_workflow_asset(
            db,
            bundle=bundle,
            run_stage_id=topic_stage_id,
            asset_type="topic_candidates",
            title="选题池",
            content_json={
                "selected_topic": deepseek_output.get("selected_topic") or "",
                "candidates": topic_candidates,
            },
            sort_order=10,
        )
        optimized_prompt = str(deepseek_output.get("optimized_prompt") or "").strip()
        if optimized_prompt:
            upsert_workflow_asset(
                db,
                bundle=bundle,
                run_stage_id=prompt_stage_id,
                asset_type="script",
                title="优化提示词",
                content_text=optimized_prompt,
                sort_order=20,
            )
        video_prompt = str(deepseek_output.get("video_prompt") or "").strip()
        if video_prompt:
            upsert_workflow_asset(
                db,
                bundle=bundle,
                run_stage_id=prompt_stage_id,
                asset_type="video_prompt",
                title="视频提示词",
                content_text=video_prompt,
                sort_order=30,
            )
        publish_copy = deepseek_output.get("publish_copy") if isinstance(deepseek_output.get("publish_copy"), dict) else {}
        if publish_copy:
            hashtags = publish_copy.get("hashtags")
            hashtags_text = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags or "")
            upsert_workflow_asset(
                db,
                bundle=bundle,
                run_stage_id=publish_stage_id,
                asset_type="publish_copy",
                title="发布稿",
                content_text="\n".join(
                    [
                        f"标题：{publish_copy.get('title') or ''}",
                        f"Hook：{publish_copy.get('hook') or ''}",
                        f"正文：{publish_copy.get('caption') or ''}",
                        f"标签：{hashtags_text}",
                    ]
                ).strip(),
                content_json=publish_copy,
                sort_order=40,
            )
        video_url = str(video_output.get("video_url") or "").strip()
        if video_url:
            upsert_workflow_asset(
                db,
                bundle=bundle,
                run_stage_id=asset_stage_id,
                asset_type="video_output",
                title="视频结果",
                content_text=video_url,
                content_json=video_output,
                mime_type="video/url",
                sort_order=50,
            )
        changed = True

    return changed


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
    capabilities = get_worker_capabilities(record)
    return {
        "id": record.id,
        "worker_code": record.worker_code,
        "group_id": record.group_id,
        "display_name": record.display_name,
        "status": effective_status,
        "reported_status": record.status,
        "machine_info": record.machine_info,
        "capabilities": capabilities,
        "max_parallel_tasks": int(record.max_parallel_tasks or 1),
        "scheduler_weight": int(record.scheduler_weight or 100),
        "dispatch_tags": capabilities,
        "current_task_title": record.current_task_title,
        "heartbeat_note": record.heartbeat_note,
        "last_heartbeat_at": record.last_heartbeat_at.isoformat() if record.last_heartbeat_at else None,
        "is_timed_out": effective_status == "offline" and record.status != "offline",
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def serialize_user_account(record: UserAccount):
    return {
        "id": record.id,
        "username": record.username,
        "display_name": record.display_name,
        "role": record.role,
        "status": record.status,
        "last_login_at": parse_datetime(record.last_login_at),
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
    }


def serialize_account_group(record: AccountGroup):
    masked_postforme_api_key = ""
    if record.postforme_api_key:
        suffix = record.postforme_api_key[-4:] if len(record.postforme_api_key) >= 4 else record.postforme_api_key
        masked_postforme_api_key = f"***{suffix}"
    return {
        "id": record.id,
        "group_name": record.group_name,
        "group_code": record.group_code,
        "owner_user_id": record.owner_user_id,
        "status": record.status,
        "remark": record.remark,
        "has_postforme_api_key": bool(record.postforme_api_key),
        "masked_postforme_api_key": masked_postforme_api_key,
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
    }


def serialize_group_member(record: UserGroupMember, user: Optional[UserAccount] = None):
    return {
        "id": record.id,
        "group_id": record.group_id,
        "user_id": record.user_id,
        "member_role": record.member_role,
        "user": serialize_user_account(user) if user else None,
        "created_at": parse_datetime(record.created_at),
    }


def serialize_worker_token(record: WorkerToken, *, plain_token: str = ""):
    return {
        "id": record.id,
        "worker_code": record.worker_code,
        "token_name": record.token_name,
        "group_id": record.group_id,
        "issued_by_user_id": record.issued_by_user_id,
        "status": record.status,
        "expired_at": parse_datetime(record.expired_at),
        "last_used_at": parse_datetime(record.last_used_at),
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
        "plain_token": plain_token,
    }


def serialize_audit_log(record: AuditLog):
    return {
        "id": record.id,
        "actor_user_id": record.actor_user_id,
        "actor_type": record.actor_type,
        "actor_code": record.actor_code,
        "action": record.action,
        "target_type": record.target_type,
        "target_id": record.target_id,
        "detail": load_json_field(record.detail_json, {}),
        "created_at": parse_datetime(record.created_at),
    }


def serialize_user_session(record: UserSession):
    return {
        "id": record.id,
        "user_id": record.user_id,
        "status": record.status,
        "expired_at": parse_datetime(record.expired_at),
        "last_used_at": parse_datetime(record.last_used_at),
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
    }


def serialize_platform_account(record: PlatformAccount):
    scopes = ensure_str_list(load_json_field(record.scope_json, []))
    profile = load_json_field(record.profile_json, {})
    return {
        "id": record.id,
        "group_id": record.group_id,
        "platform": record.platform,
        "platform_user_id": record.platform_user_id,
        "account_name": record.account_name,
        "account_handle": record.account_handle,
        "profile_url": record.profile_url,
        "avatar_url": record.avatar_url,
        "auth_type": record.auth_type,
        "status": record.status,
        "connected_by_user_id": record.connected_by_user_id,
        "token_expires_at": parse_datetime(record.token_expires_at),
        "scopes": scopes,
        "profile": profile,
        "last_synced_at": parse_datetime(record.last_synced_at),
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
    }


def serialize_oauth_session(record: OAuthSession):
    return {
        "id": record.id,
        "user_id": record.user_id,
        "group_id": record.group_id,
        "platform": record.platform,
        "status": record.status,
        "requested_scopes": ensure_str_list(load_json_field(record.requested_scope_json, [])),
        "error_message": record.error_message,
        "expired_at": parse_datetime(record.expired_at),
        "completed_at": parse_datetime(record.completed_at),
        "created_at": parse_datetime(record.created_at),
        "updated_at": parse_datetime(record.updated_at),
    }


def serialize_task_execution_record(record: TaskExecutionRecord):
    return {
        "id": record.id,
        "task_id": record.task_id,
        "group_id": record.group_id,
        "actor_user_id": record.actor_user_id,
        "worker_code": record.worker_code,
        "worker_token_id": record.worker_token_id,
        "event_type": record.event_type,
        "status_before": record.status_before,
        "status_after": record.status_after,
        "attempt_count": record.attempt_count,
        "retry_count": record.retry_count,
        "error_message": record.error_message,
        "detail": load_json_field(record.detail_json, {}),
        "created_at": parse_datetime(record.created_at),
    }


def set_worker_idle_if_online(record: WorkerNode, note: str):
    record.current_task_title = ""
    if get_effective_worker_status(record) != "offline":
        record.status = "idle"
    record.heartbeat_note = note


def sync_worker_dispatch_state(db: Session, record: WorkerNode, note: str, current_task_title: str = ""):
    running_count = count_worker_running_tasks(db, record.worker_code)
    if running_count > 0:
        record.status = "running"
        record.current_task_title = current_task_title or record.current_task_title
    else:
        record.current_task_title = ""
        if get_effective_worker_status(record) != "offline":
            record.status = "idle"
    record.heartbeat_note = note


def recover_stale_task_leases(db: Session, *, group_id: Optional[int] = None) -> int:
    statement = select(TaskRecord).where(
        TaskRecord.status == "running",
        TaskRecord.assigned_worker_code != "",
    )
    if group_id is not None:
        statement = statement.where(TaskRecord.group_id == group_id)

    recovered_count = 0
    for task in db.scalars(statement).all():
        worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == task.assigned_worker_code))
        updated_at = task.updated_at or task.created_at or utcnow()
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        lease_expired = updated_at + timedelta(seconds=get_task_lease_timeout(task)) < utcnow()
        worker_offline = worker is None or get_effective_worker_status(worker) == "offline"
        if not lease_expired and not worker_offline:
            continue

        previous_status = task.status
        state = get_task_runtime_state(task)
        state["last_error"] = "任务租约超时或 Worker 离线，已自动回收到队列"
        append_task_history(
            state,
            "lease_recovered",
            worker_code=task.assigned_worker_code,
            worker_offline=worker_offline,
            lease_timeout_seconds=get_task_lease_timeout(task),
        )
        save_task_runtime_state(task, state)
        task.status = "queued"
        task.assigned_worker_code = ""
        create_task_execution_record(
            db,
            task_id=task.id,
            group_id=task.group_id,
            event_type="lease_recovered",
            status_before=previous_status,
            status_after=task.status,
            worker_code=worker.worker_code if worker else "",
            attempt_count=int(state.get("attempt_count", 0)),
            retry_count=int(state.get("retry_count", 0)),
            error_message=state["last_error"],
            detail={"worker_offline": worker_offline},
        )
        if worker:
            sync_worker_dispatch_state(db, worker, f"任务 #{task.id} 已被调度器回收")
        recovered_count += 1

    return recovered_count


def select_claimable_task_for_worker(db: Session, worker: WorkerNode, group_id: Optional[int]) -> Optional[TaskRecord]:
    statement = (
        select(TaskRecord)
        .where(TaskRecord.status.in_(["pending", "queued"]))
        .order_by(
            case((TaskRecord.assigned_worker_code == worker.worker_code, 0), else_=1),
            case((TaskRecord.priority == "high", 0), else_=1),
            TaskRecord.id,
        )
        .limit(100)
    )
    if group_id is not None:
        statement = statement.where(TaskRecord.group_id == group_id)

    for task in db.scalars(statement).all():
        can_claim, _ = worker_can_claim_task(worker, task)
        if can_claim:
            return task

    return None


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


def get_user_or_404(db: Session, user_id: int) -> UserAccount:
    record = db.scalar(select(UserAccount).where(UserAccount.id == user_id))
    if not record:
        raise HTTPException(status_code=404, detail="用户不存在")
    return record


def get_group_or_404(db: Session, group_id: int) -> AccountGroup:
    record = db.scalar(select(AccountGroup).where(AccountGroup.id == group_id))
    if not record:
        raise HTTPException(status_code=404, detail="账号组不存在")
    return record


def get_group_member_or_404(db: Session, group_id: int, member_id: int) -> UserGroupMember:
    record = db.scalar(
        select(UserGroupMember).where(
            UserGroupMember.group_id == group_id,
            UserGroupMember.id == member_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="成员记录不存在")
    return record


def get_worker_token_or_404(db: Session, token_id: int) -> WorkerToken:
    record = db.scalar(select(WorkerToken).where(WorkerToken.id == token_id))
    if not record:
        raise HTTPException(status_code=404, detail="Worker Token 不存在")
    return record


def get_platform_account_or_404(db: Session, account_id: int) -> PlatformAccount:
    record = db.scalar(select(PlatformAccount).where(PlatformAccount.id == account_id))
    if not record:
        raise HTTPException(status_code=404, detail="平台账号不存在")
    return record


def get_oauth_session_by_state_or_404(db: Session, state: str) -> OAuthSession:
    record = db.scalar(select(OAuthSession).where(OAuthSession.state_token_hash == hash_secret(state)))
    if not record:
        raise HTTPException(status_code=404, detail="OAuth 会话不存在或已过期")
    return record


def get_active_user_session_or_401(db: Session, authorization: Optional[str]) -> tuple[UserSession, UserAccount]:
    access_token = extract_access_token(authorization)
    if not access_token:
        raise HTTPException(status_code=401, detail="缺少登录令牌")

    session_record = db.scalar(
        select(UserSession).where(UserSession.session_token_hash == hash_secret(access_token))
    )
    if not session_record or session_record.status != "active" or is_expired(session_record.expired_at):
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    user_record = get_user_or_404(db, session_record.user_id)
    if user_record.status != "active":
        raise HTTPException(status_code=403, detail="当前用户已被禁用")

    session_record.last_used_at = utcnow()
    return session_record, user_record


def build_public_business_actor() -> UserAccount:
    return UserAccount(
        username="public-test",
        password_hash="",
        display_name="公共测试模式",
        role="admin",
        status="active",
    )


def is_public_business_actor(user: UserAccount) -> bool:
    return user.id is None and (user.username or "").strip().lower() == "public-test"


def ensure_public_test_group(db: Session) -> AccountGroup:
    record = db.scalar(select(AccountGroup).where(AccountGroup.group_code == PUBLIC_TEST_GROUP_CODE))
    if record:
        if (record.status or "").strip().lower() != "active":
            record.status = "active"
            db.flush()
        return record
    record = AccountGroup(
        group_name=PUBLIC_TEST_GROUP_NAME,
        group_code=PUBLIC_TEST_GROUP_CODE,
        owner_user_id=None,
        status="active",
        remark="公共测试模式自动创建的默认账号组",
    )
    db.add(record)
    db.flush()
    return record


def get_public_business_actor(db: Session) -> UserAccount:
    admin_user = db.scalar(
        select(UserAccount)
        .where(UserAccount.status == "active", UserAccount.role == "admin")
        .order_by(UserAccount.id)
        .limit(1)
    )
    if admin_user:
        return admin_user
    fallback_user = db.scalar(
        select(UserAccount)
        .where(UserAccount.status == "active")
        .order_by(UserAccount.id)
        .limit(1)
    )
    if fallback_user:
        return fallback_user
    return build_public_business_actor()


def require_strict_active_user(db: Session, authorization: Optional[str]) -> UserAccount:
    _, user_record = get_active_user_session_or_401(db, authorization)
    return user_record


def require_active_user(db: Session, authorization: Optional[str]) -> UserAccount:
    access_token = extract_access_token(authorization)
    if access_token:
        return require_strict_active_user(db, authorization)
    if PUBLIC_BUSINESS_API_MODE:
        return get_public_business_actor(db)
    return require_strict_active_user(db, authorization)


def should_allow_user_bootstrap(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(UserAccount)) or 0) == 0


def is_admin_user(user: UserAccount) -> bool:
    return (user.role or "").strip().lower() == "admin"


def get_accessible_group_ids(db: Session, user: UserAccount) -> list[int]:
    if is_admin_user(user):
        return []
    return list(
        {
            item.group_id
            for item in db.scalars(
                select(UserGroupMember).where(UserGroupMember.user_id == user.id)
            ).all()
        }
    )


def resolve_group_scope(
    db: Session,
    user: UserAccount,
    requested_group_id: Optional[int],
    *,
    require_for_non_admin: bool = False,
) -> Optional[list[int]]:
    if requested_group_id is not None:
        get_group_or_404(db, requested_group_id)
        if not is_admin_user(user) and requested_group_id not in get_accessible_group_ids(db, user):
            raise HTTPException(status_code=403, detail="无权访问当前账号组")
        return [requested_group_id]

    if is_admin_user(user):
        return None

    group_ids = get_accessible_group_ids(db, user)
    if require_for_non_admin and not group_ids:
        raise HTTPException(status_code=403, detail="当前用户未加入任何账号组")
    return group_ids


def apply_group_scope(statement, column, group_ids: Optional[list[int]]):
    if group_ids is None:
        return statement
    return statement.where(column.in_(group_ids or [-1]))


def resolve_effective_group_id(
    db: Session,
    user: UserAccount,
    requested_group_id: Optional[int],
    *,
    required_for_non_admin_message: str,
) -> Optional[int]:
    if requested_group_id is not None:
        resolve_group_scope(db, user, requested_group_id, require_for_non_admin=True)
        return requested_group_id

    if PUBLIC_BUSINESS_API_MODE:
        return ensure_public_test_group(db).id

    if is_admin_user(user):
        return None

    group_ids = get_accessible_group_ids(db, user)
    if len(group_ids) == 1:
        return group_ids[0]

    raise HTTPException(status_code=400, detail=required_for_non_admin_message)


def get_active_worker_token_or_401(
    db: Session,
    *,
    worker_code: str,
    authorization: Optional[str],
    x_worker_token: Optional[str],
) -> WorkerToken:
    access_token = extract_access_token(authorization, x_worker_token)
    if not access_token:
        raise HTTPException(status_code=401, detail="缺少 Worker Token")

    token_record = db.scalar(
        select(WorkerToken).where(WorkerToken.token_hash == hash_secret(access_token))
    )
    if not token_record or token_record.status != "active" or is_expired(token_record.expired_at):
        raise HTTPException(status_code=401, detail="Worker Token 无效或已过期")

    if token_record.worker_code != worker_code:
        raise HTTPException(status_code=403, detail="Worker Token 与当前 Worker Code 不匹配")

    token_record.last_used_at = utcnow()
    return token_record


def resolve_worker_registration_group_id(
    db: Session,
    *,
    worker_code: str,
    authorization: Optional[str],
    x_worker_token: Optional[str],
) -> tuple[Optional[WorkerToken], int]:
    access_token = extract_access_token(authorization, x_worker_token)
    token_record = None
    if access_token:
        try:
            token_record = get_active_worker_token_or_401(
                db,
                worker_code=worker_code,
                authorization=authorization,
                x_worker_token=x_worker_token,
            )
        except HTTPException:
            if not PUBLIC_BUSINESS_API_MODE:
                raise
    elif not PUBLIC_BUSINESS_API_MODE:
        raise HTTPException(status_code=401, detail="当前操作需要 Worker Token")

    if token_record:
        return token_record, int(token_record.group_id or ensure_public_test_group(db).id)

    return None, ensure_public_test_group(db).id


def resolve_worker_task_access_context(
    db: Session,
    *,
    worker_code: str,
    authorization: Optional[str],
    x_worker_token: Optional[str],
) -> tuple[WorkerNode, int, Optional[int]]:
    access_token = extract_access_token(authorization, x_worker_token)
    token_record = None
    if access_token:
        try:
            token_record = get_active_worker_token_or_401(
                db,
                worker_code=worker_code,
                authorization=authorization,
                x_worker_token=x_worker_token,
            )
        except HTTPException:
            if not PUBLIC_BUSINESS_API_MODE:
                raise
    elif not PUBLIC_BUSINESS_API_MODE:
        raise HTTPException(status_code=401, detail="当前操作需要 Worker Token")

    worker = get_worker_or_404(db, worker_code)
    if token_record:
        if worker.group_id != token_record.group_id:
            raise HTTPException(status_code=409, detail="当前 Worker 节点归组与 Worker Token 不一致")
        return worker, int(token_record.group_id or ensure_public_test_group(db).id), token_record.id

    effective_group_id = worker.group_id or ensure_public_test_group(db).id
    if worker.group_id != effective_group_id:
        worker.group_id = effective_group_id
    return worker, int(effective_group_id), None


@app.get("/health")
def health(db: Session = Depends(get_db)):
    total_records = db.scalar(select(func.count()).select_from(AssetRecord)) or 0
    return {"ok": True, "asset_records": total_records}


@app.get("/dashboard/summary")
def dashboard_summary(
    group_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    group_scope = resolve_group_scope(db, actor_user, group_id)
    total_records = db.scalar(
        apply_group_scope(select(func.count()).select_from(AssetRecord), AssetRecord.group_id, group_scope)
    ) or 0
    latest_record = db.scalar(
        apply_group_scope(select(AssetRecord).order_by(desc(AssetRecord.id)).limit(1), AssetRecord.group_id, group_scope)
    )
    total_tasks = db.scalar(
        apply_group_scope(select(func.count()).select_from(TaskRecord), TaskRecord.group_id, group_scope)
    ) or 0
    pending_tasks = db.scalar(
        apply_group_scope(
            select(func.count()).select_from(TaskRecord).where(TaskRecord.status.in_(["pending", "queued"])),
            TaskRecord.group_id,
            group_scope,
        )
    ) or 0
    worker_items = db.scalars(
        apply_group_scope(select(WorkerNode).order_by(desc(WorkerNode.id)), WorkerNode.group_id, group_scope)
    ).all()
    online_workers = len(
        [item for item in worker_items if get_effective_worker_status(item) in ["idle", "running", "online"]]
    )
    latest_task = db.scalar(
        apply_group_scope(select(TaskRecord).order_by(desc(TaskRecord.id)).limit(1), TaskRecord.group_id, group_scope)
    )
    latest_worker = worker_items[0] if worker_items else None
    return {
        "ok": True,
        "group_id": group_id,
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


@app.post("/auth/login")
def auth_login(payload: LoginRequest, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    user = db.scalar(select(UserAccount).where(UserAccount.username == username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="当前用户已被禁用")

    plain_token = secrets.token_urlsafe(32)
    session_record = UserSession(
        user_id=user.id,
        session_token_hash=hash_secret(plain_token),
        status="active",
        expired_at=utcnow() + timedelta(days=get_user_session_expire_days()),
        last_used_at=utcnow(),
    )
    user.last_login_at = utcnow()
    db.add(session_record)
    create_audit_log(
        db,
        action="auth_login",
        target_type="user",
        target_id=str(user.id),
        actor_type="user",
        actor_code=user.username,
        actor_user_id=user.id,
        detail={"session_expire_days": get_user_session_expire_days()},
    )
    db.commit()
    db.refresh(user)
    db.refresh(session_record)
    return {
        "ok": True,
        "item": {
            "access_token": plain_token,
            "user": serialize_user_account(user),
            "session": serialize_user_session(session_record),
        },
    }


@app.get("/auth/me")
def auth_me(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    session_record, user = get_active_user_session_or_401(db, authorization)
    db.commit()
    db.refresh(session_record)
    db.refresh(user)
    return {
        "ok": True,
        "item": {
            "user": serialize_user_account(user),
            "session": serialize_user_session(session_record),
        },
    }


@app.post("/auth/logout")
def auth_logout(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    session_record, user = get_active_user_session_or_401(db, authorization)
    session_record.status = "revoked"
    session_record.last_used_at = utcnow()
    create_audit_log(
        db,
        action="auth_logout",
        target_type="session",
        target_id=str(session_record.id),
        actor_type="user",
        actor_code=user.username,
        actor_user_id=user.id,
    )
    db.commit()
    db.refresh(session_record)
    return {"ok": True, "item": serialize_user_session(session_record)}


@app.get("/oauth/providers")
def list_oauth_providers(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_oauth_provider_cards()}


@app.get("/oauth-sessions")
def list_oauth_sessions(
    platform: str = Query("", description="按平台过滤"),
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = select(OAuthSession).order_by(desc(OAuthSession.id)).limit(limit)
    statement = apply_group_scope(statement, OAuthSession.group_id, resolve_group_scope(db, actor_user, group_id))
    if platform:
        statement = statement.where(OAuthSession.platform == platform.strip().lower())
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_oauth_session(item) for item in items]}


@app.get("/platform-accounts")
def list_platform_accounts(
    platform: str = Query("", description="按平台过滤"),
    status: str = Query("", description="按状态过滤"),
    auth_type: str = Query("", description="按接入方式过滤"),
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = select(PlatformAccount).order_by(desc(PlatformAccount.id)).limit(limit)
    statement = apply_group_scope(statement, PlatformAccount.group_id, resolve_group_scope(db, actor_user, group_id))
    if platform:
        statement = statement.where(PlatformAccount.platform == platform.strip().lower())
    if status:
        statement = statement.where(PlatformAccount.status == status.strip().lower())
    if auth_type:
        statement = statement.where(PlatformAccount.auth_type == auth_type.strip().lower())
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_platform_account(item) for item in items]}


@app.patch("/platform-accounts/{account_id}")
def update_platform_account(
    account_id: int,
    payload: UpdatePlatformAccountRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    record = get_platform_account_or_404(db, account_id)
    if record.group_id is not None:
        resolve_group_scope(db, actor_user, record.group_id)
    if payload.group_id is not None:
        resolve_group_scope(db, actor_user, payload.group_id, require_for_non_admin=True)
        get_group_or_404(db, payload.group_id)
        record.group_id = payload.group_id
    if payload.account_name is not None:
        record.account_name = payload.account_name.strip() or record.account_name
    if payload.account_handle is not None:
        record.account_handle = payload.account_handle.strip()
    if payload.status is not None:
        record.status = payload.status.strip().lower() or record.status
    create_audit_log(
        db,
        action="platform_account_updated",
        target_type="platform_account",
        target_id=str(record.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"platform": record.platform, "group_id": record.group_id, "status": record.status},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_platform_account(record)}


@app.post("/postforme/social-accounts/auth-url")
def create_postforme_social_account_auth_url(
    payload: PostForMeAuthUrlRequest,
    authorization: Optional[str] = Header(default=None),
    x_postforme_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    api_key, effective_group_id = resolve_postforme_api_key(
        db,
        actor_user=actor_user,
        requested_group_id=payload.group_id,
        header_api_key=x_postforme_api_key,
    )
    platform = str(payload.platform or "").strip().lower()
    if platform not in SUPPORTED_PLATFORM_CODES:
        raise HTTPException(status_code=400, detail="当前平台暂不支持通过 Post for Me 绑定")
    response = postforme_request_json(
        "POST",
        "/social-accounts/auth-url",
        api_key,
        json_body={"platform": platform},
    )
    auth_url = str(response.get("url") or response.get("data", {}).get("url") or "").strip()
    if not auth_url:
        raise HTTPException(status_code=400, detail="Post for Me 没有返回授权地址")
    create_audit_log(
        db,
        action="postforme_auth_url_created",
        target_type="platform_account",
        target_id=platform,
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"platform": platform, "group_id": effective_group_id},
    )
    db.commit()
    return {"ok": True, "platform": platform, "auth_url": auth_url}


@app.post("/postforme/social-accounts/sync")
def sync_postforme_accounts_endpoint(
    payload: PostForMeSyncAccountsRequest,
    authorization: Optional[str] = Header(default=None),
    x_postforme_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    api_key, effective_group_id = resolve_postforme_api_key(
        db,
        actor_user=actor_user,
        requested_group_id=payload.group_id,
        header_api_key=x_postforme_api_key,
    )
    records = sync_postforme_social_accounts(
        db,
        actor_user=actor_user,
        api_key=api_key,
        platforms=payload.platforms,
        group_id=effective_group_id,
    )
    create_audit_log(
        db,
        action="postforme_accounts_synced",
        target_type="platform_account",
        target_id=str(len(records)),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"platforms": ensure_str_list(payload.platforms), "group_id": effective_group_id, "count": len(records)},
    )
    db.commit()
    return {"ok": True, "items": [serialize_platform_account(item) for item in records]}


@app.post("/postforme/social-posts")
def create_postforme_social_post(
    payload: PostForMeCreatePostRequest,
    authorization: Optional[str] = Header(default=None),
    x_postforme_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    api_key, effective_group_id = resolve_postforme_api_key(
        db,
        actor_user=actor_user,
        requested_group_id=payload.group_id,
        header_api_key=x_postforme_api_key,
    )
    social_account_ids = [str(item).strip() for item in payload.social_account_ids if str(item).strip()]
    if not social_account_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个发布账号")

    local_accounts = db.scalars(
        select(PlatformAccount).where(
            PlatformAccount.auth_type == "postforme",
            PlatformAccount.platform_user_id.in_(social_account_ids),
        )
    ).all()
    for account in local_accounts:
        if account.group_id is not None:
            resolve_group_scope(db, actor_user, account.group_id)
        if effective_group_id is not None and account.group_id not in {None, effective_group_id}:
            raise HTTPException(status_code=403, detail="选中的账号里包含其他账号组的发布账号")

    request_body = {
        "caption": str(payload.caption or "").strip(),
        "social_accounts": social_account_ids,
    }
    media_items = [{"url": url.strip()} for url in payload.media_urls if str(url).strip()]
    if media_items:
        request_body["media"] = media_items
    if str(payload.scheduled_at or "").strip():
        request_body["scheduled_at"] = str(payload.scheduled_at).strip()

    response = postforme_request_json("POST", "/social-posts", api_key, json_body=request_body)
    create_audit_log(
        db,
        action="postforme_social_post_created",
        target_type="social_post",
        target_id=str(response.get("id") or response.get("data", {}).get("id") or ""),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={
            "group_id": effective_group_id,
            "social_account_ids": social_account_ids,
            "has_media": bool(media_items),
            "scheduled_at": payload.scheduled_at,
        },
    )
    db.commit()
    return {"ok": True, "item": response}


@app.get("/oauth/{platform}/start")
def oauth_start(
    platform: str,
    request: Request,
    group_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    config = get_platform_config(platform)
    if not config["enabled"]:
        raise HTTPException(status_code=400, detail=f"{config['label']} OAuth 还没有配置 client_id / secret")

    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        group_id,
        required_for_non_admin_message="请先选择要绑定到哪个账号组",
    )
    redirect_uri = build_oauth_callback_url(request, config["code"])
    state_token = secrets.token_urlsafe(32)
    code_verifier = generate_code_verifier() if config.get("pkce_required") else ""
    session_record = OAuthSession(
        user_id=actor_user.id,
        group_id=effective_group_id,
        platform=config["code"],
        state_token_hash=hash_secret(state_token),
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        status="pending",
        requested_scope_json=json.dumps(config["scopes"], ensure_ascii=False),
        expired_at=utcnow() + timedelta(minutes=15),
    )
    db.add(session_record)
    db.flush()

    auth_params = {
        config.get("authorization_client_param", "client_id"): config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scope_separator"].join(config["scopes"]),
        "state": state_token,
    }
    if platform == "youtube":
        auth_params["access_type"] = "offline"
        auth_params["include_granted_scopes"] = "true"
        auth_params["prompt"] = "consent"
    if platform in {"facebook", "instagram"}:
        auth_params["auth_type"] = "rerequest"
    if config.get("pkce_required"):
        auth_params["code_challenge"] = build_code_challenge(code_verifier)
        auth_params["code_challenge_method"] = "S256"

    auth_url = build_query_url(config["auth_url"], auth_params)
    create_audit_log(
        db,
        action="oauth_session_started",
        target_type="oauth_session",
        target_id=str(session_record.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"platform": config["code"], "group_id": effective_group_id},
    )
    db.commit()
    db.refresh(session_record)
    return {
        "ok": True,
        "auth_url": auth_url,
        "item": serialize_oauth_session(session_record),
    }


@app.get("/oauth/{platform}/callback")
def oauth_callback(
    platform: str,
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
    db: Session = Depends(get_db),
):
    normalized_platform = str(platform or "").strip().lower()
    try:
        config = get_platform_config(normalized_platform)
    except HTTPException as exc:
        return RedirectResponse(
            build_accounts_redirect_url(normalized_platform, "error", exc.detail),
            status_code=302,
        )

    if not state:
        return RedirectResponse(
            build_accounts_redirect_url(normalized_platform, "error", "缺少 OAuth state"),
            status_code=302,
        )

    session_record = None
    try:
        session_record = get_oauth_session_by_state_or_404(db, state)
        if session_record.platform != config["code"]:
            raise HTTPException(status_code=400, detail="OAuth 平台与会话不匹配")
        if is_expired(session_record.expired_at):
            session_record.status = "expired"
            db.commit()
            raise HTTPException(status_code=400, detail="OAuth 会话已过期，请重新发起连接")
        if error:
            message = error_description or error
            session_record.status = "failed"
            session_record.error_message = message
            session_record.completed_at = utcnow()
            db.commit()
            raise HTTPException(status_code=400, detail=message)
        if not code:
            raise HTTPException(status_code=400, detail="OAuth 回调缺少 code")

        actor_user = get_user_or_404(db, session_record.user_id)
        token_data = exchange_oauth_code(
            config["code"],
            config,
            code,
            session_record.redirect_uri or build_oauth_callback_url(request, config["code"]),
            session_record.code_verifier or "",
        )
        profile = fetch_platform_profile(config["code"], token_data["access_token"])
        if not profile.get("platform_user_id"):
            raise HTTPException(status_code=400, detail="已拿到令牌，但无法识别平台账号 ID")

        existing = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == config["code"],
                PlatformAccount.platform_user_id == profile["platform_user_id"],
            )
        )
        if existing and existing.group_id != session_record.group_id and existing.group_id is not None:
            raise HTTPException(status_code=409, detail="该平台账号已绑定到其他账号组")

        account_record = existing or PlatformAccount(
            group_id=session_record.group_id,
            platform=config["code"],
            platform_user_id=profile["platform_user_id"],
        )
        if existing is None:
            db.add(account_record)

        account_record.group_id = session_record.group_id
        account_record.account_name = profile["account_name"]
        account_record.account_handle = profile["account_handle"]
        account_record.profile_url = profile["profile_url"]
        account_record.avatar_url = profile["avatar_url"]
        account_record.auth_type = "oauth2"
        account_record.status = "active"
        account_record.connected_by_user_id = actor_user.id
        account_record.access_token = token_data["access_token"]
        account_record.refresh_token = token_data["refresh_token"]
        account_record.token_type = token_data["token_type"]
        account_record.token_expires_at = token_data["expires_at"]
        account_record.scope_json = json.dumps(token_data["scopes"], ensure_ascii=False)
        account_record.profile_json = json.dumps(profile["profile"], ensure_ascii=False)
        account_record.last_synced_at = utcnow()

        session_record.status = "completed"
        session_record.error_message = ""
        session_record.completed_at = utcnow()

        create_audit_log(
            db,
            action="platform_account_connected",
            target_type="platform_account",
            target_id=f"{config['code']}:{profile['platform_user_id']}",
            actor_type="user",
            actor_code=actor_user.username,
            actor_user_id=actor_user.id,
            detail={"platform": config["code"], "group_id": session_record.group_id},
        )
        db.commit()
        return RedirectResponse(
            build_accounts_redirect_url(config["code"], "success", f"{config['label']} 账号已接入"),
            status_code=302,
        )
    except HTTPException as exc:
        if session_record is not None:
            session_record.status = "failed"
            session_record.error_message = str(exc.detail)
            session_record.completed_at = utcnow()
            db.commit()
        return RedirectResponse(
            build_accounts_redirect_url(normalized_platform, "error", str(exc.detail)),
            status_code=302,
        )
    except Exception as exc:
        if session_record is not None:
            session_record.status = "failed"
            session_record.error_message = str(exc)
            session_record.completed_at = utcnow()
            db.commit()
        return RedirectResponse(
            build_accounts_redirect_url(normalized_platform, "error", str(exc)),
            status_code=302,
        )


@app.get("/users")
def list_users(
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_strict_active_user(db, authorization)
    items = db.scalars(select(UserAccount).order_by(desc(UserAccount.id)).limit(limit)).all()
    return {"ok": True, "items": [serialize_user_account(item) for item in items]}


@app.post("/users")
def create_user(
    payload: CreateUserRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization) if not should_allow_user_bootstrap(db) else None
    username = payload.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    existing = db.scalar(select(UserAccount).where(UserAccount.username == username))
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    record = UserAccount(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip() or username,
        role=payload.role.strip() or "admin",
        status=payload.status.strip() or "active",
    )
    db.add(record)
    create_audit_log(
        db,
        action="user_created",
        target_type="user",
        target_id=username,
        actor_type="user" if actor_user else "system",
        actor_code=actor_user.username if actor_user else "bootstrap",
        actor_user_id=actor_user.id if actor_user else None,
        detail={"role": record.role, "status": record.status},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_user_account(record)}


@app.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    record = get_user_or_404(db, user_id)
    if payload.display_name is not None:
        record.display_name = payload.display_name.strip() or record.display_name
    if payload.role is not None:
        record.role = payload.role.strip() or record.role
    if payload.status is not None:
        record.status = payload.status.strip() or record.status
    if payload.password:
        record.password_hash = hash_password(payload.password)
    create_audit_log(
        db,
        action="user_updated",
        target_type="user",
        target_id=str(record.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"role": record.role, "status": record.status},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_user_account(record)}


@app.get("/groups")
def list_groups(
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    if PUBLIC_BUSINESS_API_MODE and (db.scalar(select(func.count()).select_from(AccountGroup)) or 0) == 0:
        ensure_public_test_group(db)
        db.commit()
    statement = select(AccountGroup).order_by(desc(AccountGroup.id)).limit(limit)
    statement = apply_group_scope(statement, AccountGroup.id, resolve_group_scope(db, actor_user, None))
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_account_group(item) for item in items]}


@app.post("/groups")
def create_group(
    payload: CreateGroupRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    group_name = payload.group_name.strip()
    if not group_name:
        raise HTTPException(status_code=400, detail="账号组名称不能为空")
    group_code = normalize_code(payload.group_code or group_name, "group")
    existing = db.scalar(select(AccountGroup).where(AccountGroup.group_code == group_code))
    if existing:
        raise HTTPException(status_code=409, detail="账号组编码已存在")

    if payload.owner_user_id is not None:
        get_user_or_404(db, payload.owner_user_id)

    record = AccountGroup(
        group_name=group_name,
        group_code=group_code,
        owner_user_id=payload.owner_user_id,
        status=payload.status.strip() or "active",
        remark=payload.remark.strip(),
        postforme_api_key=payload.postforme_api_key.strip(),
    )
    db.add(record)
    db.flush()
    if payload.owner_user_id is not None:
        db.add(
            UserGroupMember(
                user_id=payload.owner_user_id,
                group_id=record.id,
                member_role="owner",
            )
        )
    create_audit_log(
        db,
        action="group_created",
        target_type="group",
        target_id=group_code,
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={
            "owner_user_id": payload.owner_user_id,
            "has_postforme_api_key": bool(record.postforme_api_key),
        },
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_account_group(record)}


@app.patch("/groups/{group_id}")
def update_group(
    group_id: int,
    payload: UpdateGroupRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    record = get_group_or_404(db, group_id)
    if payload.group_name is not None:
        record.group_name = payload.group_name.strip() or record.group_name
    if payload.owner_user_id is not None:
        get_user_or_404(db, payload.owner_user_id)
        record.owner_user_id = payload.owner_user_id
    if payload.status is not None:
        record.status = payload.status.strip() or record.status
    if payload.remark is not None:
        record.remark = payload.remark.strip()
    if payload.postforme_api_key is not None:
        record.postforme_api_key = payload.postforme_api_key.strip()
    create_audit_log(
        db,
        action="group_updated",
        target_type="group",
        target_id=str(group_id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={
            "status": record.status,
            "has_postforme_api_key": bool(record.postforme_api_key),
        },
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_account_group(record)}


@app.get("/groups/{group_id}/members")
def list_group_members(
    group_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    resolve_group_scope(db, actor_user, group_id)
    get_group_or_404(db, group_id)
    items = db.scalars(
        select(UserGroupMember)
        .where(UserGroupMember.group_id == group_id)
        .order_by(desc(UserGroupMember.id))
    ).all()
    users = {
        user.id: user
        for user in db.scalars(
            select(UserAccount).where(UserAccount.id.in_([item.user_id for item in items] or [-1]))
        ).all()
    }
    return {
        "ok": True,
        "items": [serialize_group_member(item, users.get(item.user_id)) for item in items],
    }


@app.post("/groups/{group_id}/members")
def create_group_member(
    group_id: int,
    payload: CreateGroupMemberRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    resolve_group_scope(db, actor_user, group_id)
    get_group_or_404(db, group_id)
    user = get_user_or_404(db, payload.user_id)
    existing = db.scalar(
        select(UserGroupMember).where(
            UserGroupMember.group_id == group_id,
            UserGroupMember.user_id == payload.user_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="该用户已在当前账号组中")
    record = UserGroupMember(
        group_id=group_id,
        user_id=payload.user_id,
        member_role=payload.member_role.strip() or "editor",
    )
    db.add(record)
    create_audit_log(
        db,
        action="group_member_created",
        target_type="group_member",
        target_id=f"{group_id}:{payload.user_id}",
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"member_role": record.member_role},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_group_member(record, user)}


@app.patch("/groups/{group_id}/members/{member_id}")
def update_group_member(
    group_id: int,
    member_id: int,
    payload: UpdateGroupMemberRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    resolve_group_scope(db, actor_user, group_id)
    record = get_group_member_or_404(db, group_id, member_id)
    record.member_role = payload.member_role.strip() or record.member_role
    user = get_user_or_404(db, record.user_id)
    create_audit_log(
        db,
        action="group_member_updated",
        target_type="group_member",
        target_id=str(member_id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"member_role": record.member_role},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_group_member(record, user)}


@app.get("/worker-tokens")
def list_worker_tokens(
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    statement = select(WorkerToken).order_by(desc(WorkerToken.id)).limit(limit)
    statement = apply_group_scope(
        statement,
        WorkerToken.group_id,
        resolve_group_scope(db, actor_user, group_id),
    )
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_worker_token(item) for item in items]}


@app.post("/worker-tokens")
def create_worker_token(
    payload: CreateWorkerTokenRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    worker_code = payload.worker_code.strip()
    if not worker_code:
        raise HTTPException(status_code=400, detail="Worker Code 不能为空")
    if payload.group_id is None and not is_admin_user(actor_user):
        raise HTTPException(status_code=400, detail="非管理员签发 Worker Token 必须指定账号组")
    group_scope = resolve_group_scope(
        db,
        actor_user,
        payload.group_id,
        require_for_non_admin=True,
    )
    if payload.issued_by_user_id is not None:
        get_user_or_404(db, payload.issued_by_user_id)

    plain_token = secrets.token_urlsafe(24)
    record = WorkerToken(
        worker_code=worker_code,
        token_name=payload.token_name.strip() or f"{worker_code}-token",
        token_hash=hash_secret(plain_token),
        group_id=(group_scope[0] if group_scope else payload.group_id),
        issued_by_user_id=payload.issued_by_user_id,
        status="active",
        expired_at=utcnow() + timedelta(days=payload.expire_days),
    )
    db.add(record)
    create_audit_log(
        db,
        action="worker_token_created",
        target_type="worker_token",
        target_id=worker_code,
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": payload.group_id, "expire_days": payload.expire_days},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_worker_token(record, plain_token=plain_token)}


@app.post("/worker-tokens/{token_id}/revoke")
def revoke_worker_token(
    token_id: int,
    payload: RevokeWorkerTokenRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_strict_active_user(db, authorization)
    record = get_worker_token_or_404(db, token_id)
    if record.group_id is None and not is_admin_user(actor_user):
        raise HTTPException(status_code=403, detail="当前用户无权操作未归组的 Worker Token")
    resolve_group_scope(db, actor_user, record.group_id)
    record.status = "revoked"
    create_audit_log(
        db,
        action="worker_token_revoked",
        target_type="worker_token",
        target_id=str(token_id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"reason": payload.reason},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_worker_token(record)}


@app.get("/audit-logs")
def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_strict_active_user(db, authorization)
    items = db.scalars(select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)).all()
    return {"ok": True, "items": [serialize_audit_log(item) for item in items]}


@app.get("/task-executions")
def list_task_executions(
    task_id: int = Query(0, ge=0),
    worker_code: str = Query(""),
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    group_scope = resolve_group_scope(db, actor_user, group_id)
    statement = select(TaskExecutionRecord).order_by(desc(TaskExecutionRecord.id)).limit(limit)
    if task_id > 0:
        statement = (
            select(TaskExecutionRecord)
            .where(TaskExecutionRecord.task_id == task_id)
            .order_by(desc(TaskExecutionRecord.id))
            .limit(limit)
        )
    statement = apply_group_scope(
        statement,
        TaskExecutionRecord.group_id,
        group_scope,
    )
    if worker_code.strip():
        statement = statement.where(TaskExecutionRecord.worker_code == worker_code.strip())
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_task_execution_record(item) for item in items]}


@app.post("/worker/register")
def register_worker(
    payload: WorkerRegisterRequest,
    authorization: Optional[str] = Header(default=None),
    x_worker_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    worker_code = payload.worker_code.strip()
    if not worker_code:
        raise HTTPException(status_code=400, detail="Worker Code 不能为空")

    token_record, effective_group_id = resolve_worker_registration_group_id(
        db,
        worker_code=worker_code,
        authorization=authorization,
        x_worker_token=x_worker_token,
    )
    record = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == worker_code))
    if not record:
        record = WorkerNode(
            worker_code=worker_code,
            group_id=effective_group_id,
            display_name=payload.display_name.strip() or worker_code,
            status="idle",
            machine_info=payload.machine_info.strip(),
            capabilities=json.dumps(payload.capabilities, ensure_ascii=False),
            max_parallel_tasks=payload.max_parallel_tasks,
            scheduler_weight=payload.scheduler_weight,
            current_task_title="",
            heartbeat_note=payload.heartbeat_note.strip() or "Worker 已完成注册",
            last_heartbeat_at=utcnow(),
        )
        db.add(record)
    else:
        record.group_id = effective_group_id
        record.display_name = payload.display_name.strip() or record.display_name
        record.status = "idle"
        record.machine_info = payload.machine_info.strip()
        record.capabilities = json.dumps(payload.capabilities, ensure_ascii=False)
        record.max_parallel_tasks = payload.max_parallel_tasks
        record.scheduler_weight = payload.scheduler_weight
        record.heartbeat_note = payload.heartbeat_note.strip() or "Worker 已重新注册"
        record.last_heartbeat_at = utcnow()

    create_audit_log(
        db,
        action="worker_registered",
        target_type="worker",
        target_id=worker_code,
        actor_type="worker",
        actor_code=worker_code,
        detail={
            "worker_token_id": token_record.id if token_record else None,
            "group_id": effective_group_id,
            "max_parallel_tasks": payload.max_parallel_tasks,
            "scheduler_weight": payload.scheduler_weight,
        },
    )
    db.commit()
    db.refresh(record)
    if token_record:
        db.refresh(token_record)
    return {
        "ok": True,
        "item": serialize_worker_node(record),
        "worker_token": serialize_worker_token(token_record) if token_record else None,
    }


@app.post("/assets/upload-text")
def upload_text(
    payload: UploadTextRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    client = get_s3_client()
    bucket = get_bucket_name()
    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        payload.group_id,
        required_for_non_admin_message="非管理员上传文件必须指定账号组",
    )

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
            group_id=effective_group_id,
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
    group_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    client = get_s3_client()
    bucket = get_bucket_name()
    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        group_id,
        required_for_non_admin_message="非管理员上传文件必须指定账号组",
    )

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
            group_id=effective_group_id,
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
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    client = get_s3_client()
    bucket = get_bucket_name()
    normalized_prefix = prefix.strip("/")
    group_scope = resolve_group_scope(db, actor_user, group_id)
    allowed_keys = None
    if group_scope is not None:
        allowed_keys = set(
            db.scalars(
                apply_group_scope(
                    select(AssetRecord.asset_key).where(AssetRecord.prefix == normalized_prefix),
                    AssetRecord.group_id,
                    group_scope,
                )
            ).all()
        )

    try:
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{normalized_prefix}/" if normalized_prefix else "",
            MaxKeys=limit if allowed_keys is None else max(limit * 5, 100),
        )
        items = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if allowed_keys is not None and key not in allowed_keys:
                continue
            items.append(
                {
                    "key": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "url": build_object_url(key),
                }
            )
            if len(items) >= limit:
                break

        return {
            "ok": True,
            "bucket": bucket,
            "prefix": normalized_prefix,
            "group_id": group_id,
            "items": items,
        }
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/assets/records")
def list_asset_records(
    prefix: str = Query("assets"),
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    normalized_prefix = prefix.strip("/")
    statement = select(AssetRecord).where(AssetRecord.prefix == normalized_prefix).order_by(desc(AssetRecord.id)).limit(limit)
    statement = apply_group_scope(
        statement,
        AssetRecord.group_id,
        resolve_group_scope(db, actor_user, group_id),
    )
    records = db.scalars(statement).all()
    return {
        "ok": True,
        "prefix": normalized_prefix,
        "group_id": group_id,
        "items": [serialize_asset_record(record) for record in records],
    }


@app.get("/assets/presign")
def presign_get_url(
    key: str,
    expires_in: int = Query(3600, ge=60, le=86400),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    client = get_s3_client()
    bucket = get_bucket_name()
    record = db.scalar(select(AssetRecord).where(AssetRecord.asset_key == key).order_by(desc(AssetRecord.id)))
    if record:
        if record.group_id is None and not is_admin_user(actor_user):
            raise HTTPException(status_code=403, detail="当前用户无权访问未归组资产")
        resolve_group_scope(db, actor_user, record.group_id)
    elif not is_admin_user(actor_user):
        raise HTTPException(status_code=403, detail="当前用户无权访问未登记资产")

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
def delete_asset(
    key: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    client = get_s3_client()
    bucket = get_bucket_name()
    record = db.scalar(
        select(AssetRecord).where(AssetRecord.asset_key == key).order_by(desc(AssetRecord.id))
    )
    if record:
        if record.group_id is None and not is_admin_user(actor_user):
            raise HTTPException(status_code=403, detail="当前用户无权删除未归组资产")
        resolve_group_scope(db, actor_user, record.group_id)
    elif not is_admin_user(actor_user):
        raise HTTPException(status_code=403, detail="当前用户无权删除未登记资产")

    try:
        client.delete_object(Bucket=bucket, Key=key)
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


@app.get("/agent-flow/templates")
def list_agent_flow_templates(
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    if (db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0) == 0:
        ensure_default_agent_flow_template(db)
        db.commit()
    statement = select(WorkflowTemplate).order_by(desc(WorkflowTemplate.id)).limit(limit)
    statement = apply_group_scope(
        statement,
        WorkflowTemplate.group_id,
        resolve_group_scope(db, actor_user, group_id),
    )
    items = db.scalars(statement).all()
    versions = {}
    version_ids = [item.current_version_id for item in items if item.current_version_id]
    if version_ids:
        versions = {
            item.id: item
            for item in db.scalars(
                select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id.in_(version_ids))
            ).all()
        }
    return {
        "ok": True,
        "items": [serialize_workflow_template(item, versions.get(item.current_version_id)) for item in items],
    }


@app.get("/agent-flow/templates/{template_id}/versions")
def list_agent_flow_template_versions(
    template_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    template = get_workflow_template_or_404(db, template_id)
    if template.group_id is not None:
        resolve_group_scope(db, actor_user, template.group_id)
    items = db.scalars(
        select(WorkflowTemplateVersion)
        .where(WorkflowTemplateVersion.template_id == template_id)
        .order_by(desc(WorkflowTemplateVersion.version_no), desc(WorkflowTemplateVersion.id))
    ).all()
    return {"ok": True, "items": [serialize_workflow_template_version(item) for item in items]}


@app.post("/agent-flow/template-versions/{version_id}/publish")
def publish_agent_flow_template_version(
    version_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    version = get_workflow_template_version_or_404(db, version_id)
    template = get_workflow_template_or_404(db, version.template_id)
    if template.group_id is not None:
        resolve_group_scope(db, actor_user, template.group_id)
    sibling_versions = db.scalars(
        select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.template_id == template.id)
    ).all()
    for item in sibling_versions:
        item.is_published = item.id == version.id
    template.current_version_id = version.id
    create_audit_log(
        db,
        action="agent_flow_template_version_published",
        target_type="workflow_template",
        target_id=str(template.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"template_id": template.id, "version_id": version.id},
    )
    db.commit()
    db.refresh(template)
    db.refresh(version)
    return {"ok": True, "item": serialize_workflow_template(template, version)}


@app.post("/agent-flow/template-versions/{version_id}/apply-preset")
def apply_agent_flow_template_version_preset(
    version_id: int,
    payload: ApplyWorkflowTemplatePresetRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    version = get_workflow_template_version_or_404(db, version_id)
    template = get_workflow_template_or_404(db, version.template_id)
    if template.group_id is not None:
        resolve_group_scope(db, actor_user, template.group_id)
    preset_type = str(payload.preset_type or "").strip()
    preset_code = str(payload.preset_code or "").strip()
    if not preset_type or not preset_code:
        raise HTTPException(status_code=400, detail="预设类型和预设编码不能为空")
    preset = find_agent_flow_preset(preset_type, preset_code)
    if not preset:
        raise HTTPException(status_code=404, detail="指定预设不存在")

    if preset_type == "model_presets":
        version.default_model_config_json = json.dumps(preset.get("config") or {}, ensure_ascii=False)
    elif preset_type == "stage_chain_presets":
        version.stage_schema_json = json.dumps(preset.get("stage_schema") or [], ensure_ascii=False)
    elif preset_type == "style_bibles":
        version.style_bible_json = json.dumps(preset, ensure_ascii=False)
    elif preset_type == "shot_bibles":
        rules = preset.get("rules") if isinstance(preset.get("rules"), dict) else preset
        version.shot_bible_json = json.dumps(rules, ensure_ascii=False)
    elif preset_type == "character_bibles":
        prompt_blocks = load_json_field(version.prompt_blocks_json, {})
        prompt_blocks["character_bible"] = preset
        version.prompt_blocks_json = json.dumps(prompt_blocks, ensure_ascii=False)
    else:
        raise HTTPException(status_code=400, detail="当前预设类型暂不支持应用到模板版本")

    create_audit_log(
        db,
        action="agent_flow_template_preset_applied",
        target_type="workflow_template_version",
        target_id=str(version.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"template_id": template.id, "preset_type": preset_type, "preset_code": preset_code},
    )
    db.commit()
    db.refresh(version)
    return {"ok": True, "item": serialize_workflow_template_version(version)}


@app.get("/agent-flow/projects")
def list_agent_flow_projects(
    group_id: Optional[int] = Query(default=None),
    status: str = Query(default=""),
    limit: int = Query(50, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = select(WorkflowProject).order_by(desc(WorkflowProject.id)).limit(limit)
    statement = apply_group_scope(statement, WorkflowProject.group_id, resolve_group_scope(db, actor_user, group_id))
    if status:
        statement = statement.where(WorkflowProject.status == status.strip())
    items = db.scalars(statement).all()
    template_ids = [item.template_id for item in items if item.template_id]
    templates = {
        item.id: item
        for item in db.scalars(select(WorkflowTemplate).where(WorkflowTemplate.id.in_(template_ids or [-1]))).all()
    }
    run_counts = {
        project_id: count
        for project_id, count in db.execute(
            select(WorkflowRun.project_id, func.count(WorkflowRun.id))
            .where(WorkflowRun.project_id.in_([item.id for item in items] or [-1]))
            .group_by(WorkflowRun.project_id)
        ).all()
    }
    return {
        "ok": True,
        "items": [
            {**serialize_workflow_project(item, template=templates.get(item.template_id)), "run_count": int(run_counts.get(item.id, 0))}
            for item in items
        ],
    }


@app.post("/agent-flow/projects")
def create_agent_flow_project(
    payload: CreateWorkflowProjectRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        payload.group_id,
        required_for_non_admin_message="请先选择账号组",
    )
    template = None
    if payload.template_id is not None:
        template = get_workflow_template_or_404(db, payload.template_id)
        if template.group_id is not None:
            resolve_group_scope(db, actor_user, template.group_id)
    project_name = str(payload.project_name or "").strip()
    if not project_name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    base_code = normalize_code(project_name, fallback_prefix="project")
    project_code = base_code
    suffix = 1
    while db.scalar(select(WorkflowProject).where(WorkflowProject.project_code == project_code)):
        suffix += 1
        project_code = f"{base_code}-{suffix}"
    record = WorkflowProject(
        group_id=effective_group_id,
        project_code=project_code,
        project_name=project_name,
        template_id=payload.template_id,
        platform=str(payload.platform or "tiktok").strip() or "tiktok",
        subject_domain=str(payload.subject_domain or "").strip(),
        status="active",
        owner_user_id=actor_user.id,
        remark=str(payload.remark or "").strip(),
    )
    db.add(record)
    create_audit_log(
        db,
        action="agent_flow_project_created",
        target_type="workflow_project",
        target_id=str(project_code),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": effective_group_id, "template_id": payload.template_id},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_workflow_project(record, template=template)}


@app.get("/agent-flow/projects/{project_id}")
def get_agent_flow_project(
    project_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    record = get_workflow_project_or_404(db, project_id)
    resolve_group_scope(db, actor_user, record.group_id)
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.id == record.template_id)) if record.template_id else None
    run_count = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.project_id == record.id)) or 0
    return {"ok": True, "item": {**serialize_workflow_project(record, template=template), "run_count": int(run_count)}}


@app.put("/agent-flow/projects/{project_id}")
def update_agent_flow_project(
    project_id: int,
    payload: UpdateWorkflowProjectRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    record = get_workflow_project_or_404(db, project_id)
    resolve_group_scope(db, actor_user, record.group_id)
    if payload.project_name is not None:
        next_name = str(payload.project_name).strip()
        if not next_name:
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        record.project_name = next_name
    if payload.template_id is not None:
        template = get_workflow_template_or_404(db, payload.template_id)
        if template.group_id is not None:
            resolve_group_scope(db, actor_user, template.group_id)
        record.template_id = payload.template_id
    if payload.platform is not None:
        record.platform = str(payload.platform).strip() or record.platform
    if payload.subject_domain is not None:
        record.subject_domain = str(payload.subject_domain).strip()
    if payload.status is not None:
        record.status = str(payload.status).strip() or record.status
    if payload.remark is not None:
        record.remark = str(payload.remark)
    create_audit_log(
        db,
        action="agent_flow_project_updated",
        target_type="workflow_project",
        target_id=str(record.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": record.group_id, "template_id": record.template_id},
    )
    db.commit()
    db.refresh(record)
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.id == record.template_id)) if record.template_id else None
    return {"ok": True, "item": serialize_workflow_project(record, template=template)}


@app.get("/agent-flow/projects/{project_id}/runs")
def list_agent_flow_project_runs(
    project_id: int,
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    project = get_workflow_project_or_404(db, project_id)
    resolve_group_scope(db, actor_user, project.group_id)
    items = db.scalars(
        select(WorkflowRun).where(WorkflowRun.project_id == project_id).order_by(desc(WorkflowRun.id)).limit(limit)
    ).all()
    changed = False
    for item in items:
        changed = sync_workflow_run_state(db, item) or changed
    if changed:
        db.commit()
    template_ids = [item.template_id for item in items if item.template_id]
    version_ids = [item.template_version_id for item in items if item.template_version_id]
    task_ids = [item.task_record_id for item in items if item.task_record_id]
    templates = {
        item.id: item
        for item in db.scalars(select(WorkflowTemplate).where(WorkflowTemplate.id.in_(template_ids or [-1]))).all()
    }
    versions = {
        item.id: item
        for item in db.scalars(select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id.in_(version_ids or [-1]))).all()
    }
    bundles = {
        item.run_id: item
        for item in db.scalars(
            select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id.in_([item.id for item in items] or [-1]))
        ).all()
    }
    tasks = {
        item.id: item for item in db.scalars(select(TaskRecord).where(TaskRecord.id.in_(task_ids or [-1]))).all()
    }
    return {
        "ok": True,
        "project": serialize_workflow_project(project, template=templates.get(project.template_id)),
        "items": [
            serialize_workflow_run(
                item,
                template=templates.get(item.template_id),
                template_version=versions.get(item.template_version_id),
                bundle=bundles.get(item.id),
                task=tasks.get(item.task_record_id),
            )
            for item in items
        ],
    }


@app.get("/agent-flow/settings/presets")
def get_agent_flow_settings_presets(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, **get_agent_flow_settings_catalog()}


@app.get("/agent-flow/settings/style-bibles")
def list_agent_flow_style_bibles(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_default_agent_flow_style_bibles()}


@app.get("/agent-flow/settings/character-bibles")
def list_agent_flow_character_bibles(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_default_agent_flow_character_bibles()}


@app.get("/agent-flow/settings/shot-bibles")
def list_agent_flow_shot_bibles(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_default_agent_flow_shot_bibles()}


@app.get("/agent-flow/settings/model-presets")
def list_agent_flow_model_presets(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_default_agent_flow_model_presets()}


@app.get("/agent-flow/settings/stage-chain-presets")
def list_agent_flow_stage_chain_presets(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_default_agent_flow_stage_chain_presets()}


@app.get("/agent-flow/settings/platform-presets")
def list_agent_flow_platform_presets(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    require_active_user(db, authorization)
    return {"ok": True, "items": get_default_agent_flow_platform_presets()}


@app.get("/agent-flow/summary")
def agent_flow_summary(
    group_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    group_scope = resolve_group_scope(db, actor_user, group_id)
    total = db.scalar(
        apply_group_scope(select(func.count()).select_from(WorkflowRun), WorkflowRun.group_id, group_scope)
    ) or 0
    pending = db.scalar(
        apply_group_scope(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.status.in_(["pending", "queued"])),
            WorkflowRun.group_id,
            group_scope,
        )
    ) or 0
    running = db.scalar(
        apply_group_scope(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.status == "running"),
            WorkflowRun.group_id,
            group_scope,
        )
    ) or 0
    success = db.scalar(
        apply_group_scope(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.status == "success"),
            WorkflowRun.group_id,
            group_scope,
        )
    ) or 0
    failed = db.scalar(
        apply_group_scope(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.status == "failed"),
            WorkflowRun.group_id,
            group_scope,
        )
    ) or 0
    latest = db.scalar(
        apply_group_scope(select(WorkflowRun).order_by(desc(WorkflowRun.id)).limit(1), WorkflowRun.group_id, group_scope)
    )
    if latest:
        sync_workflow_run_state(db, latest)
        db.commit()
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == latest.id)) if latest else None
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.id == latest.template_id)) if latest else None
    version = (
        db.scalar(select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id == latest.template_version_id))
        if latest and latest.template_version_id
        else None
    )
    task = db.scalar(select(TaskRecord).where(TaskRecord.id == latest.task_record_id)) if latest and latest.task_record_id else None
    return {
        "ok": True,
        "total": total,
        "pending": pending,
        "running": running,
        "success": success,
        "failed": failed,
        "latest": serialize_workflow_run(latest, template=template, template_version=version, bundle=bundle, task=task) if latest else None,
    }


@app.post("/agent-flow/runs")
def create_agent_flow_run(
    payload: CreateAgentFlowRunRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    if (db.scalar(select(func.count()).select_from(WorkflowTemplate)) or 0) == 0:
        ensure_default_agent_flow_template(db)
        db.flush()

    template = get_workflow_template_or_404(db, payload.template_id)
    if template.group_id is not None:
        resolve_group_scope(db, actor_user, template.group_id)
    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        payload.group_id if payload.group_id is not None else template.group_id,
        required_for_non_admin_message="请先选择账号组",
    )
    version_id = payload.template_version_id or template.current_version_id
    if not version_id:
        raise HTTPException(status_code=400, detail="当前模板还没有可用版本")
    version = get_workflow_template_version_or_404(db, version_id)
    if version.template_id != template.id:
        raise HTTPException(status_code=400, detail="模板版本与模板不匹配")
    project = None
    if payload.project_id is not None:
        project = get_workflow_project_or_404(db, payload.project_id)
        resolve_group_scope(db, actor_user, project.group_id)
        if project.group_id and project.group_id != effective_group_id:
            raise HTTPException(status_code=400, detail="所选项目与账号组不一致")

    brief_payload = payload.brief_payload if isinstance(payload.brief_payload, dict) else {}
    platform_targets = ensure_str_list(payload.platform_targets)
    task_payload = build_agent_flow_task_payload_from_template(version, brief_payload, platform_targets)
    runtime_state = {
        "attempt_count": 0,
        "retry_count": 0,
        "manual_retry_count": 0,
        "max_retries": task_payload["execution"]["max_retries"],
        "last_error": "",
        "history": [],
    }
    append_task_history(runtime_state, "created", source_type="agent_flow")
    task_priority = "high" if payload.priority <= 50 else "normal"
    topic_seed = str(brief_payload.get("topic_seed") or "").strip()
    title = str(payload.title or "").strip() or f"{template.template_name}-{topic_seed[:20] or '新运行'}"
    task = TaskRecord(
        title=title,
        task_type="agent_flow",
        source_type="manual",
        source_value=topic_seed or str(brief_payload.get("goal") or "").strip(),
        status="pending",
        priority=task_priority,
        group_id=effective_group_id,
        created_by_user_id=actor_user.id,
        triggered_by_user_id=actor_user.id,
        payload_json=json.dumps(task_payload, ensure_ascii=False),
        result_json=json.dumps(runtime_state, ensure_ascii=False),
    )
    db.add(task)
    db.flush()

    run = WorkflowRun(
        group_id=effective_group_id,
        project_id=project.id if project else None,
        template_id=template.id,
        template_version_id=version.id,
        task_record_id=task.id,
        run_code=f"run-{uuid.uuid4().hex[:10]}",
        run_type=payload.run_type.strip() or "single",
        title=title,
        brief_payload_json=json.dumps(brief_payload, ensure_ascii=False),
        platform_targets_json=json.dumps(platform_targets or [task_payload["agent_flow"]["platform"]], ensure_ascii=False),
        status=task.status,
        current_stage_code="topic_generate",
        priority=payload.priority,
        source_mode=payload.source_mode.strip() or "manual",
        created_by_user_id=actor_user.id,
        triggered_by_user_id=actor_user.id,
    )
    db.add(run)
    db.flush()

    stage_schema = load_json_field(version.stage_schema_json, get_default_agent_flow_stage_schema())
    for index, stage in enumerate(stage_schema, start=1):
        stage_code = str(stage.get("code") or f"stage_{index}").strip()
        record = WorkflowRunStage(
            run_id=run.id,
            stage_code=stage_code,
            stage_name=str(stage.get("name") or stage_code).strip(),
            stage_order=index,
            worker_code="",
            required_capability=str(stage.get("required_capability") or "").strip(),
            input_payload_json=json.dumps(brief_payload if stage_code == "brief_collect" else {}, ensure_ascii=False),
            output_payload_json=json.dumps({}, ensure_ascii=False),
            status="success" if stage_code == "brief_collect" else ("queued" if stage_code == "topic_generate" else "pending"),
            retry_count=0,
            error_message="",
            started_at=utcnow() if stage_code == "brief_collect" else None,
            finished_at=utcnow() if stage_code == "brief_collect" else None,
        )
        db.add(record)

    bundle = WorkflowAssetBundle(
        group_id=effective_group_id,
        run_id=run.id,
        bundle_code=f"bundle-{uuid.uuid4().hex[:10]}",
        bundle_name=title,
        content_type="short_video",
        primary_platform=(platform_targets[0] if platform_targets else task_payload["agent_flow"]["platform"]),
        status="draft",
        summary=topic_seed,
    )
    db.add(bundle)

    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        actor_user_id=actor_user.id,
        event_type="created",
        status_before="",
        status_after=task.status,
        detail={"title": task.title, "task_type": task.task_type, "source_type": task.source_type},
    )
    create_audit_log(
        db,
        action="agent_flow_run_created",
        target_type="workflow_run",
        target_id=str(run.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": effective_group_id, "template_id": template.id, "task_id": task.id},
    )
    db.commit()
    db.refresh(run)
    db.refresh(bundle)
    db.refresh(task)
    return {
        "ok": True,
        "item": serialize_workflow_run(run, template=template, template_version=version, bundle=bundle, task=task),
    }


@app.get("/agent-flow/runs")
def list_agent_flow_runs(
    status: str = Query("", description="按状态过滤"),
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = select(WorkflowRun).order_by(desc(WorkflowRun.id)).limit(limit)
    statement = apply_group_scope(statement, WorkflowRun.group_id, resolve_group_scope(db, actor_user, group_id))
    if status:
        statement = statement.where(WorkflowRun.status == status.strip())
    items = db.scalars(statement).all()
    changed = False
    for item in items:
        changed = sync_workflow_run_state(db, item) or changed
    if changed:
        db.commit()
    template_ids = [item.template_id for item in items if item.template_id]
    version_ids = [item.template_version_id for item in items if item.template_version_id]
    task_ids = [item.task_record_id for item in items if item.task_record_id]
    templates = {
        item.id: item
        for item in db.scalars(select(WorkflowTemplate).where(WorkflowTemplate.id.in_(template_ids or [-1]))).all()
    }
    versions = {
        item.id: item
        for item in db.scalars(
            select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id.in_(version_ids or [-1]))
        ).all()
    }
    bundles = {
        item.run_id: item
        for item in db.scalars(
            select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id.in_([item.id for item in items] or [-1]))
        ).all()
    }
    tasks = {
        item.id: item for item in db.scalars(select(TaskRecord).where(TaskRecord.id.in_(task_ids or [-1]))).all()
    }
    return {
        "ok": True,
        "items": [
            serialize_workflow_run(
                item,
                template=templates.get(item.template_id),
                template_version=versions.get(item.template_version_id),
                bundle=bundles.get(item.id),
                task=tasks.get(item.task_record_id),
            )
            for item in items
        ],
    }


@app.get("/agent-flow/runs/{run_id}")
def get_agent_flow_run(
    run_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    run = get_workflow_run_or_404(db, run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    changed = sync_workflow_run_state(db, run)
    if changed:
        db.commit()
        db.refresh(run)
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.id == run.template_id)) if run.template_id else None
    version = (
        db.scalar(select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id == run.template_version_id))
        if run.template_version_id
        else None
    )
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == run.id))
    task = db.scalar(select(TaskRecord).where(TaskRecord.id == run.task_record_id)) if run.task_record_id else None
    return {
        "ok": True,
        "item": serialize_workflow_run(run, template=template, template_version=version, bundle=bundle, task=task),
    }


@app.get("/agent-flow/runs/{run_id}/stages")
def list_agent_flow_run_stages(
    run_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    run = get_workflow_run_or_404(db, run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    changed = sync_workflow_run_state(db, run)
    if changed:
        db.commit()
    items = db.scalars(
        select(WorkflowRunStage).where(WorkflowRunStage.run_id == run_id).order_by(WorkflowRunStage.stage_order)
    ).all()
    return {"ok": True, "items": [serialize_workflow_stage(item) for item in items]}


@app.get("/agent-flow/run-stages/{stage_id}")
def get_agent_flow_run_stage(
    stage_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    stage = get_workflow_stage_or_404(db, stage_id)
    run = get_workflow_run_or_404(db, stage.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    changed = sync_workflow_run_state(db, run)
    if changed:
        db.commit()
        db.refresh(stage)
    return {"ok": True, "item": serialize_workflow_stage(stage)}


@app.get("/agent-flow/runs/{run_id}/assets")
def list_agent_flow_run_assets(
    run_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    run = get_workflow_run_or_404(db, run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    changed = sync_workflow_run_state(db, run)
    if changed:
        db.commit()
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == run_id))
    if not bundle:
        return {"ok": True, "bundle": None, "items": []}
    items = db.scalars(
        select(WorkflowAsset)
        .where(WorkflowAsset.bundle_id == bundle.id)
        .order_by(WorkflowAsset.sort_order, WorkflowAsset.id)
    ).all()
    return {"ok": True, "bundle": serialize_workflow_bundle(bundle), "items": [serialize_workflow_asset(item) for item in items]}


@app.post("/agent-flow/runs/{run_id}/assets/select")
def select_agent_flow_run_asset(
    run_id: int,
    payload: SelectWorkflowAssetRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    run = get_workflow_run_or_404(db, run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == run_id))
    if not bundle:
        raise HTTPException(status_code=404, detail="当前运行还没有资产包")
    asset = get_workflow_asset_or_404(db, payload.asset_id)
    if asset.bundle_id != bundle.id:
        raise HTTPException(status_code=400, detail="所选资产不属于当前运行")
    siblings = db.scalars(
        select(WorkflowAsset).where(
            WorkflowAsset.bundle_id == bundle.id,
            WorkflowAsset.asset_type == asset.asset_type,
        )
    ).all()
    for item in siblings:
        item.is_selected = item.id == asset.id
    create_audit_log(
        db,
        action="agent_flow_asset_selected",
        target_type="workflow_asset",
        target_id=str(asset.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"run_id": run.id, "bundle_id": bundle.id, "asset_type": asset.asset_type},
    )
    db.commit()
    db.refresh(asset)
    return {"ok": True, "item": serialize_workflow_asset(asset)}


@app.get("/agent-flow/asset-bundles/{bundle_id}")
def get_agent_flow_asset_bundle(
    bundle_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    bundle = get_workflow_bundle_or_404(db, bundle_id)
    run = get_workflow_run_or_404(db, bundle.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    changed = sync_workflow_run_state(db, run)
    if changed:
        db.commit()
        db.refresh(bundle)
    assets = db.scalars(
        select(WorkflowAsset)
        .where(WorkflowAsset.bundle_id == bundle.id)
        .order_by(WorkflowAsset.asset_type, WorkflowAsset.sort_order, WorkflowAsset.id)
    ).all()
    links = db.scalars(
        select(WorkflowPublishLink)
        .where(WorkflowPublishLink.bundle_id == bundle.id)
        .order_by(desc(WorkflowPublishLink.id))
    ).all()
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.id == run.template_id)) if run.template_id else None
    version = (
        db.scalar(select(WorkflowTemplateVersion).where(WorkflowTemplateVersion.id == run.template_version_id))
        if run.template_version_id
        else None
    )
    task = db.scalar(select(TaskRecord).where(TaskRecord.id == run.task_record_id)) if run.task_record_id else None
    return {
        "ok": True,
        "bundle": serialize_workflow_bundle(bundle),
        "run": serialize_workflow_run(run, template=template, template_version=version, bundle=bundle, task=task),
        "assets": [serialize_workflow_asset(item) for item in assets],
        "publish_links": [serialize_workflow_publish_link(item) for item in links],
    }


@app.get("/agent-flow/assets/{asset_id}")
def get_agent_flow_asset(
    asset_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    asset = get_workflow_asset_or_404(db, asset_id)
    bundle = get_workflow_bundle_or_404(db, asset.bundle_id)
    run = get_workflow_run_or_404(db, bundle.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    return {
        "ok": True,
        "item": serialize_workflow_asset(asset),
        "bundle": serialize_workflow_bundle(bundle),
        "run_id": run.id,
    }


@app.put("/agent-flow/assets/{asset_id}")
def update_agent_flow_asset(
    asset_id: int,
    payload: UpdateWorkflowAssetRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    asset = get_workflow_asset_or_404(db, asset_id)
    bundle = get_workflow_bundle_or_404(db, asset.bundle_id)
    run = get_workflow_run_or_404(db, bundle.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    if payload.title is not None:
        asset.title = str(payload.title).strip()
    if payload.content_text is not None:
        asset.content_text = str(payload.content_text)
    if payload.content_json is not None:
        asset.content_json = json.dumps(payload.content_json, ensure_ascii=False)
    create_audit_log(
        db,
        action="agent_flow_asset_updated",
        target_type="workflow_asset",
        target_id=str(asset.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"run_id": run.id, "bundle_id": bundle.id, "asset_type": asset.asset_type},
    )
    db.commit()
    db.refresh(asset)
    return {"ok": True, "item": serialize_workflow_asset(asset)}


@app.post("/agent-flow/runs/{run_id}/retry")
def retry_agent_flow_run(
    run_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    run = get_workflow_run_or_404(db, run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    task = get_task_or_404(db, int(run.task_record_id or 0))
    state = get_task_runtime_state(task)
    state["manual_retry_count"] = int(state.get("manual_retry_count", 0)) + 1
    state["last_error"] = ""
    append_task_history(state, "manual_retry", source="workflow_run")
    save_task_runtime_state(task, state)
    previous_status = task.status
    if task.assigned_worker_code:
        worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == task.assigned_worker_code))
        if worker:
            set_worker_idle_if_online(worker, f"工作流运行 #{run.id} 已重试")
    task.assigned_worker_code = ""
    task.status = "queued"
    task.triggered_by_user_id = actor_user.id
    run.status = "queued"
    run.current_stage_code = "topic_generate"
    run.finished_at = None
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == run.id))
    if bundle:
        bundle.status = "draft"
    for stage in db.scalars(select(WorkflowRunStage).where(WorkflowRunStage.run_id == run.id)).all():
        stage.worker_code = ""
        stage.error_message = ""
        stage.output_payload_json = json.dumps({}, ensure_ascii=False)
        stage.retry_count = 0
        if stage.stage_code == "brief_collect":
            stage.status = "success"
        elif stage.stage_code == "topic_generate":
            stage.status = "queued"
            stage.started_at = None
            stage.finished_at = None
        else:
            stage.status = "pending"
            stage.started_at = None
            stage.finished_at = None
    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        actor_user_id=actor_user.id,
        event_type="manual_retry",
        status_before=previous_status,
        status_after=task.status,
        attempt_count=int(state.get("attempt_count", 0)),
        retry_count=int(state.get("retry_count", 0)),
        detail={"workflow_run_id": run.id, "manual_retry_count": int(state.get("manual_retry_count", 0))},
    )
    create_audit_log(
        db,
        action="agent_flow_run_retried",
        target_type="workflow_run",
        target_id=str(run.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": run.group_id, "task_id": task.id},
    )
    db.commit()
    db.refresh(run)
    return {"ok": True, "item": serialize_workflow_run(run, task=task, bundle=bundle)}


@app.post("/agent-flow/run-stages/{stage_id}/retry")
def retry_agent_flow_run_stage(
    stage_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    stage = get_workflow_stage_or_404(db, stage_id)
    run = get_workflow_run_or_404(db, stage.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    if stage.stage_code == "brief_collect":
        raise HTTPException(status_code=400, detail="Brief 阶段无需单独重跑")
    task = get_task_or_404(db, int(run.task_record_id or 0))
    state = get_task_runtime_state(task)
    state["manual_retry_count"] = int(state.get("manual_retry_count", 0)) + 1
    state["last_error"] = ""
    append_task_history(state, "manual_stage_retry", source="workflow_stage", stage_code=stage.stage_code)
    save_task_runtime_state(task, state)
    previous_status = task.status
    if task.assigned_worker_code:
        worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == task.assigned_worker_code))
        if worker:
            set_worker_idle_if_online(worker, f"阶段 {stage.stage_name} 已手动重跑")
    task.assigned_worker_code = ""
    task.status = "queued"
    task.triggered_by_user_id = actor_user.id
    run.status = "queued"
    run.current_stage_code = stage.stage_code
    run.finished_at = None
    bundle = db.scalar(select(WorkflowAssetBundle).where(WorkflowAssetBundle.run_id == run.id))
    if bundle:
        bundle.status = "draft"
    stages = db.scalars(
        select(WorkflowRunStage).where(WorkflowRunStage.run_id == run.id).order_by(WorkflowRunStage.stage_order)
    ).all()
    for item in stages:
        if item.stage_order < stage.stage_order:
            continue
        item.worker_code = ""
        item.error_message = ""
        if item.stage_order == stage.stage_order:
            item.retry_count = int(item.retry_count or 0) + 1
            item.status = "queued"
        else:
            item.retry_count = 0
            item.status = "pending"
        item.output_payload_json = json.dumps({}, ensure_ascii=False)
        item.started_at = None
        item.finished_at = None
    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        actor_user_id=actor_user.id,
        event_type="manual_stage_retry",
        status_before=previous_status,
        status_after=task.status,
        attempt_count=int(state.get("attempt_count", 0)),
        retry_count=int(state.get("retry_count", 0)),
        detail={
            "workflow_run_id": run.id,
            "stage_id": stage.id,
            "stage_code": stage.stage_code,
            "manual_retry_count": int(state.get("manual_retry_count", 0)),
        },
    )
    create_audit_log(
        db,
        action="agent_flow_stage_retried",
        target_type="workflow_stage",
        target_id=str(stage.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"run_id": run.id, "stage_code": stage.stage_code, "task_id": task.id},
    )
    db.commit()
    db.refresh(stage)
    return {"ok": True, "item": serialize_workflow_stage(stage), "run_id": run.id}


@app.post("/agent-flow/asset-bundles/{bundle_id}/push-publish-center")
def push_agent_flow_bundle_to_publish_center(
    bundle_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    bundle = get_workflow_bundle_or_404(db, bundle_id)
    run = get_workflow_run_or_404(db, bundle.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    sync_workflow_run_state(db, run)
    assets = db.scalars(
        select(WorkflowAsset).where(WorkflowAsset.bundle_id == bundle.id).order_by(WorkflowAsset.sort_order, WorkflowAsset.id)
    ).all()
    publish_asset = next((item for item in assets if item.asset_type == "publish_copy"), None)
    video_asset = next((item for item in assets if item.asset_type == "video_output"), None)
    publish_payload = load_json_field(publish_asset.content_json, {}) if publish_asset else {}
    hashtags = publish_payload.get("hashtags")
    hashtags_text = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags or "")
    title_text = str(publish_payload.get("title") or bundle.bundle_name or run.title).strip()
    body_text = str(publish_payload.get("caption") or publish_asset.content_text or "").strip()
    if hashtags_text:
        body_text = f"{body_text}\n\n{hashtags_text}".strip()
    link = WorkflowPublishLink(
        group_id=bundle.group_id,
        bundle_id=bundle.id,
        publish_draft_id=None,
        platform=bundle.primary_platform,
        title_text=title_text,
        body_text=body_text,
        cover_asset_id=None,
        video_asset_id=video_asset.id if video_asset else None,
        status="pushed",
        pushed_at=utcnow(),
    )
    db.add(link)
    bundle.status = "published"
    create_audit_log(
        db,
        action="agent_flow_bundle_pushed_publish_center",
        target_type="workflow_bundle",
        target_id=str(bundle.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"run_id": run.id, "platform": bundle.primary_platform},
    )
    db.commit()
    db.refresh(link)
    return {
        "ok": True,
        "item": serialize_workflow_publish_link(link),
        "draft": {
            "source": "agent_flow_bundle",
            "bundle_id": bundle.id,
            "run_id": run.id,
            "task_id": run.task_record_id,
            "group_id": run.group_id,
            "task_title": run.title,
            "selected_topic": bundle.summary,
            "optimized_prompt": "",
            "video_prompt": "",
            "video_url": video_asset.content_text if video_asset else "",
            "publish": {
                "title": title_text,
                "hook": str(publish_payload.get("hook") or "").strip(),
                "caption": str(publish_payload.get("caption") or "").strip(),
                "hashtags": hashtags_text,
            },
            "copied_at": iso_now(),
        },
    }


@app.get("/agent-flow/asset-bundles/{bundle_id}/publish-links")
def list_agent_flow_publish_links(
    bundle_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    bundle = get_workflow_bundle_or_404(db, bundle_id)
    run = get_workflow_run_or_404(db, bundle.run_id)
    resolve_group_scope(db, actor_user, run.group_id)
    items = db.scalars(
        select(WorkflowPublishLink)
        .where(WorkflowPublishLink.bundle_id == bundle_id)
        .order_by(desc(WorkflowPublishLink.id))
    ).all()
    return {"ok": True, "items": [serialize_workflow_publish_link(item) for item in items]}


@app.post("/tasks")
def create_task(
    payload: CreateTaskRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    if payload.group_id is None and not is_admin_user(actor_user):
        raise HTTPException(status_code=400, detail="非管理员创建任务必须指定账号组")
    effective_group_id = resolve_effective_group_id(
        db,
        actor_user,
        payload.group_id,
        required_for_non_admin_message="请先选择任务归属账号组",
    )

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
        group_id=effective_group_id,
        created_by_user_id=actor_user.id,
        triggered_by_user_id=actor_user.id,
        payload_json=json.dumps(normalized_payload, ensure_ascii=False),
        result_json=json.dumps(runtime_state, ensure_ascii=False),
    )
    db.add(record)
    db.flush()
    create_task_execution_record(
        db,
        task_id=record.id,
        group_id=record.group_id,
        actor_user_id=actor_user.id,
        event_type="created",
        status_before="",
        status_after=record.status,
        detail={
            "title": record.title,
            "task_type": record.task_type,
            "source_type": record.source_type,
        },
    )
    create_audit_log(
        db,
        action="task_created",
        target_type="task",
        target_id=str(record.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": record.group_id, "priority": record.priority},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_task_record(record)}


@app.get("/tasks")
def list_tasks(
    status: str = Query("", description="按状态过滤"),
    task_type: str = Query("", description="按任务类型过滤"),
    group_id: Optional[int] = Query(default=None, description="按账号组过滤"),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = select(TaskRecord).order_by(desc(TaskRecord.id)).limit(limit)
    statement = apply_group_scope(
        statement,
        TaskRecord.group_id,
        resolve_group_scope(db, actor_user, group_id),
    )
    if status:
        statement = statement.where(TaskRecord.status == status)
    if task_type:
        statement = statement.where(TaskRecord.task_type == task_type)
    items = db.scalars(statement).all()
    return {"ok": True, "items": [serialize_task_record(item) for item in items]}


@app.get("/tasks/summary")
def tasks_summary(
    task_type: str = Query("", description="按任务类型过滤"),
    group_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    group_scope = resolve_group_scope(db, actor_user, group_id)
    
    def apply_task_type_filter(statement):
        if task_type:
            return statement.where(TaskRecord.task_type == task_type)
        return statement

    total = db.scalar(
        apply_task_type_filter(
            apply_group_scope(select(func.count()).select_from(TaskRecord), TaskRecord.group_id, group_scope)
        )
    ) or 0
    pending = db.scalar(
        apply_task_type_filter(
            apply_group_scope(
                select(func.count()).select_from(TaskRecord).where(TaskRecord.status.in_(["pending", "queued"])),
                TaskRecord.group_id,
                group_scope,
            )
        )
    ) or 0
    running = db.scalar(
        apply_task_type_filter(
            apply_group_scope(
                select(func.count()).select_from(TaskRecord).where(TaskRecord.status == "running"),
                TaskRecord.group_id,
                group_scope,
            )
        )
    ) or 0
    success = db.scalar(
        apply_task_type_filter(
            apply_group_scope(
                select(func.count()).select_from(TaskRecord).where(TaskRecord.status == "success"),
                TaskRecord.group_id,
                group_scope,
            )
        )
    ) or 0
    failed = db.scalar(
        apply_task_type_filter(
            apply_group_scope(
                select(func.count()).select_from(TaskRecord).where(TaskRecord.status == "failed"),
                TaskRecord.group_id,
                group_scope,
            )
        )
    ) or 0
    latest = db.scalar(
        apply_task_type_filter(
            apply_group_scope(select(TaskRecord).order_by(desc(TaskRecord.id)).limit(1), TaskRecord.group_id, group_scope)
        )
    )
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
def worker_heartbeat(
    payload: WorkerHeartbeatRequest,
    authorization: Optional[str] = Header(default=None),
    x_worker_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    access_token = extract_access_token(authorization, x_worker_token)
    actor_user = None
    token_record = None
    if access_token:
        session_record = db.scalar(
            select(UserSession).where(UserSession.session_token_hash == hash_secret(access_token))
        )
        if session_record and session_record.status == "active" and not is_expired(session_record.expired_at):
            actor_user = get_user_or_404(db, session_record.user_id)
            if actor_user.status != "active":
                raise HTTPException(status_code=403, detail="当前用户已被禁用")
            session_record.last_used_at = utcnow()
        else:
            try:
                token_record = get_active_worker_token_or_401(
                    db,
                    worker_code=payload.worker_code,
                    authorization=authorization,
                    x_worker_token=x_worker_token,
                )
            except HTTPException:
                if PUBLIC_BUSINESS_API_MODE:
                    actor_user = get_public_business_actor(db)
                else:
                    raise

    if not actor_user and not token_record:
        if PUBLIC_BUSINESS_API_MODE:
            actor_user = get_public_business_actor(db)
        else:
            raise HTTPException(status_code=401, detail="提交 Worker 心跳需要用户会话或 Worker Token")

    effective_group_id = (
        token_record.group_id
        if token_record
        else resolve_effective_group_id(
            db,
            actor_user,
            payload.group_id,
            required_for_non_admin_message="非管理员登记 Worker 节点必须指定账号组",
        )
    )
    record = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == payload.worker_code))
    if not record:
        record = WorkerNode(
            worker_code=payload.worker_code,
            group_id=effective_group_id,
            display_name=payload.display_name,
            status=payload.status,
            machine_info=payload.machine_info,
            capabilities=json.dumps(payload.capabilities, ensure_ascii=False),
            max_parallel_tasks=payload.max_parallel_tasks,
            scheduler_weight=payload.scheduler_weight,
            current_task_title=payload.current_task_title,
            heartbeat_note=payload.heartbeat_note,
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(record)
    else:
        record.group_id = effective_group_id
        record.display_name = payload.display_name
        record.status = payload.status
        record.machine_info = payload.machine_info
        record.capabilities = json.dumps(payload.capabilities, ensure_ascii=False)
        record.max_parallel_tasks = payload.max_parallel_tasks
        record.scheduler_weight = payload.scheduler_weight
        record.current_task_title = payload.current_task_title
        record.heartbeat_note = payload.heartbeat_note
        record.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_worker_node(record)}


@app.get("/workers")
def list_workers(
    group_id: Optional[int] = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = select(WorkerNode).order_by(desc(WorkerNode.id)).limit(limit)
    statement = apply_group_scope(
        statement,
        WorkerNode.group_id,
        resolve_group_scope(db, actor_user, group_id),
    )
    items = db.scalars(statement).all()
    serialized_items = []
    for item in items:
        serialized = serialize_worker_node(item)
        running_task_count = count_worker_running_tasks(db, item.worker_code)
        serialized["running_task_count"] = running_task_count
        serialized["available_slots"] = max(0, serialized["max_parallel_tasks"] - running_task_count)
        serialized_items.append(serialized)
    return {"ok": True, "items": serialized_items}


@app.delete("/workers/{worker_code}")
def delete_worker(
    worker_code: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    worker = get_worker_or_404(db, worker_code)
    if worker.group_id is None and not is_admin_user(actor_user):
        raise HTTPException(status_code=403, detail="当前用户无权删除未归组 Worker 节点")
    resolve_group_scope(db, actor_user, worker.group_id)

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
    create_audit_log(
        db,
        action="worker_deleted",
        target_type="worker",
        target_id=worker_code,
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"cleared_task_count": len(assigned_tasks)},
    )
    db.delete(worker)
    db.commit()
    return {"ok": True, "item": deleted_item, "cleared_task_count": len(assigned_tasks)}


@app.get("/workers/summary")
def workers_summary(
    group_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    statement = apply_group_scope(
        select(WorkerNode).order_by(desc(WorkerNode.id)),
        WorkerNode.group_id,
        resolve_group_scope(db, actor_user, group_id),
    )
    items = db.scalars(statement).all()
    total = len(items)
    online = len([item for item in items if get_effective_worker_status(item) in ["idle", "running", "online"]])
    offline = total - online
    latest = items[0] if items else None
    total_slots = sum(max(1, int(item.max_parallel_tasks or 1)) for item in items)
    busy_slots = sum(count_worker_running_tasks(db, item.worker_code) for item in items)
    return {
        "ok": True,
        "total": total,
        "online": online,
        "offline": offline,
        "total_slots": total_slots,
        "busy_slots": busy_slots,
        "available_slots": max(0, total_slots - busy_slots),
        "latest": serialize_worker_node(latest) if latest else None,
    }


@app.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    payload: UpdateTaskRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    record = get_task_or_404(db, task_id)
    if record.group_id is None and not is_admin_user(actor_user):
        raise HTTPException(status_code=403, detail="当前用户无权修改未归组任务")
    resolve_group_scope(db, actor_user, record.group_id)

    previous_status = record.status
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
            if worker_record.group_id != record.group_id:
                raise HTTPException(status_code=409, detail="指定 Worker 不属于当前任务账号组")
            missing_capabilities = sorted(
                set(get_task_required_capabilities(record)) - set(get_worker_capabilities(worker_record))
            )
            if missing_capabilities:
                raise HTTPException(
                    status_code=409,
                    detail=f"指定 Worker 缺少任务能力：{', '.join(missing_capabilities)}",
                )
            preferred_worker_codes = get_task_preferred_worker_codes(record)
            if preferred_worker_codes and normalized_worker_code not in preferred_worker_codes:
                raise HTTPException(status_code=409, detail="当前任务已绑定其他 Worker")
            record.assigned_worker_code = normalized_worker_code
        else:
            record.assigned_worker_code = ""

    if payload.status is not None:
        record.status = payload.status.strip() or record.status

    if payload.result is not None:
        save_task_runtime_state(record, payload.result)

    record.triggered_by_user_id = actor_user.id

    if previous_worker_code and previous_worker_code != record.assigned_worker_code:
        previous_worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == previous_worker_code))
        if previous_worker:
            sync_worker_dispatch_state(db, previous_worker, f"已取消任务 #{record.id} 指派")

    assigned_worker = None
    if record.assigned_worker_code:
        assigned_worker = db.scalar(
            select(WorkerNode).where(WorkerNode.worker_code == record.assigned_worker_code)
        )

    if assigned_worker:
        if record.status == "running":
            sync_worker_dispatch_state(db, assigned_worker, f"处理中：任务 #{record.id}", record.title)
        elif record.status in ["success", "failed", "cancelled", "pending", "queued"]:
            sync_worker_dispatch_state(db, assigned_worker, f"最近处理任务 #{record.id} 状态：{record.status}")

    create_task_execution_record(
        db,
        task_id=record.id,
        group_id=record.group_id,
        actor_user_id=actor_user.id,
        event_type="manually_updated",
        status_before=previous_status,
        status_after=record.status,
        worker_code=record.assigned_worker_code,
        attempt_count=int(get_task_runtime_state(record).get("attempt_count", 0)),
        retry_count=int(get_task_runtime_state(record).get("retry_count", 0)),
        detail={"assigned_worker_code": record.assigned_worker_code},
    )
    create_audit_log(
        db,
        action="task_updated",
        target_type="task",
        target_id=str(record.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"status": record.status, "assigned_worker_code": record.assigned_worker_code},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "item": serialize_task_record(record)}


@app.post("/worker/tasks/claim")
def claim_task(
    payload: WorkerTaskClaimRequest,
    authorization: Optional[str] = Header(default=None),
    x_worker_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    worker, effective_group_id, worker_token_id = resolve_worker_task_access_context(
        db,
        worker_code=payload.worker_code,
        authorization=authorization,
        x_worker_token=x_worker_token,
    )
    recover_stale_task_leases(db, group_id=effective_group_id)

    current_running_task = db.scalar(
        select(TaskRecord)
        .where(TaskRecord.assigned_worker_code == payload.worker_code, TaskRecord.status == "running")
        .order_by(desc(TaskRecord.id))
        .limit(1)
    )
    available_slots = get_worker_available_slots(db, worker)
    if current_running_task and available_slots <= 0:
        return {"ok": True, "item": serialize_task_record(current_running_task), "reused": True}

    task = select_claimable_task_for_worker(db, worker, effective_group_id)
    if not task:
        sync_worker_dispatch_state(db, worker, "暂无可领取任务")
        db.commit()
        return {"ok": True, "item": None}

    state = get_task_runtime_state(task)
    state["attempt_count"] = int(state.get("attempt_count", 0)) + 1
    state["last_error"] = ""
    append_task_history(
        state,
        "claimed",
        worker_code=payload.worker_code,
        required_capabilities=get_task_required_capabilities(task),
    )
    save_task_runtime_state(task, state)

    previous_status = task.status
    task.status = "running"
    task.assigned_worker_code = payload.worker_code
    worker.status = "running"
    worker.current_task_title = task.title
    worker.heartbeat_note = f"已领取任务 #{task.id}，剩余槽位 {max(0, available_slots - 1)}"
    worker.last_heartbeat_at = utcnow()
    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        event_type="claimed",
        status_before=previous_status,
        status_after=task.status,
        worker_code=payload.worker_code,
        worker_token_id=worker_token_id,
        attempt_count=int(state.get("attempt_count", 0)),
        retry_count=int(state.get("retry_count", 0)),
        detail={
            "reused": False,
            "priority": task.priority,
            "required_capabilities": get_task_required_capabilities(task),
            "preferred_worker_codes": get_task_preferred_worker_codes(task),
        },
    )
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task), "reused": False}


@app.post("/worker/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    payload: WorkerTaskCompleteRequest,
    authorization: Optional[str] = Header(default=None),
    x_worker_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    worker, effective_group_id, worker_token_id = resolve_worker_task_access_context(
        db,
        worker_code=payload.worker_code,
        authorization=authorization,
        x_worker_token=x_worker_token,
    )
    task = get_task_or_404(db, task_id)
    if effective_group_id is not None and task.group_id != effective_group_id:
        raise HTTPException(status_code=403, detail="当前 Worker Token 无权完成其他账号组任务")
    if task.assigned_worker_code != payload.worker_code:
        raise HTTPException(status_code=409, detail="该任务未分配给当前 Worker")

    state = get_task_runtime_state(task)
    state["last_error"] = ""
    state["output"] = payload.result
    append_task_history(state, "completed", worker_code=payload.worker_code)
    save_task_runtime_state(task, state)

    previous_status = task.status
    task.status = "success"
    ensure_asset_record_from_result(db, task, payload.result)
    sync_worker_dispatch_state(db, worker, f"最近完成任务 #{task.id}")
    worker.last_heartbeat_at = utcnow()
    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        event_type="completed",
        status_before=previous_status,
        status_after=task.status,
        worker_code=payload.worker_code,
        worker_token_id=worker_token_id,
        attempt_count=int(state.get("attempt_count", 0)),
        retry_count=int(state.get("retry_count", 0)),
        detail={"result": payload.result},
    )
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task)}


@app.post("/worker/tasks/{task_id}/fail")
def fail_task(
    task_id: int,
    payload: WorkerTaskFailRequest,
    authorization: Optional[str] = Header(default=None),
    x_worker_token: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    worker, effective_group_id, worker_token_id = resolve_worker_task_access_context(
        db,
        worker_code=payload.worker_code,
        authorization=authorization,
        x_worker_token=x_worker_token,
    )
    task = get_task_or_404(db, task_id)
    if effective_group_id is not None and task.group_id != effective_group_id:
        raise HTTPException(status_code=403, detail="当前 Worker Token 无权回写其他账号组任务")
    if task.assigned_worker_code != payload.worker_code:
        raise HTTPException(status_code=409, detail="该任务未分配给当前 Worker")

    state = get_task_runtime_state(task)
    max_retries = int(state.get("max_retries", 2))
    next_retry_count = int(state.get("retry_count", 0))
    will_retry = payload.retryable and next_retry_count < max_retries

    previous_status = task.status
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

    sync_worker_dispatch_state(
        db,
        worker,
        f"任务 #{task.id} {'已进入重试队列' if will_retry else '执行失败'}",
    )
    worker.last_heartbeat_at = utcnow()
    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        event_type="retry_queued" if will_retry else "failed",
        status_before=previous_status,
        status_after=task.status,
        worker_code=payload.worker_code,
        worker_token_id=worker_token_id,
        attempt_count=int(state.get("attempt_count", 0)),
        retry_count=int(state.get("retry_count", 0)),
        error_message=payload.error_message,
        detail={"retryable": payload.retryable, "result": payload.result},
    )
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task), "will_retry": will_retry}


@app.post("/tasks/{task_id}/retry")
def retry_task(
    task_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor_user = require_active_user(db, authorization)
    task = get_task_or_404(db, task_id)
    if task.group_id is None and not is_admin_user(actor_user):
        raise HTTPException(status_code=403, detail="当前用户无权重试未归组任务")
    resolve_group_scope(db, actor_user, task.group_id)
    state = get_task_runtime_state(task)
    state["manual_retry_count"] = int(state.get("manual_retry_count", 0)) + 1
    state["last_error"] = ""
    append_task_history(state, "manual_retry")
    save_task_runtime_state(task, state)
    previous_status = task.status

    if task.assigned_worker_code:
        worker = db.scalar(select(WorkerNode).where(WorkerNode.worker_code == task.assigned_worker_code))
        if worker:
            set_worker_idle_if_online(worker, f"任务 #{task.id} 已手动重试")

    task.assigned_worker_code = ""
    task.status = "queued"
    task.triggered_by_user_id = actor_user.id
    create_task_execution_record(
        db,
        task_id=task.id,
        group_id=task.group_id,
        actor_user_id=actor_user.id,
        event_type="manual_retry",
        status_before=previous_status,
        status_after=task.status,
        attempt_count=int(state.get("attempt_count", 0)),
        retry_count=int(state.get("retry_count", 0)),
        detail={"manual_retry_count": int(state.get("manual_retry_count", 0))},
    )
    create_audit_log(
        db,
        action="task_retried",
        target_type="task",
        target_id=str(task.id),
        actor_type="user",
        actor_code=actor_user.username,
        actor_user_id=actor_user.id,
        detail={"group_id": task.group_id, "manual_retry_count": int(state.get("manual_retry_count", 0))},
    )
    db.commit()
    db.refresh(task)
    return {"ok": True, "item": serialize_task_record(task)}
