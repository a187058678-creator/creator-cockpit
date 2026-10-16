import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import requests
from botocore.client import Config


TASK_PAYLOAD_SCHEMA_VERSION = "creator-task/v1"
ALLOWED_DEDUPE_PROFILES = {"light", "balanced", "aggressive"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def env_int(name: str, default: int, minimum: int) -> int:
    raw_value = env(name, str(default))
    try:
        return max(minimum, int(raw_value))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw_value = env(name, str(default))
    try:
        return float(raw_value)
    except ValueError:
        return default


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
    return json.loads(json.dumps(presets[normalized_profile]))


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
            "lease_timeout_seconds": 1800,
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
    normalized = json.loads(json.dumps(defaults))

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
    normalized["source"]["start_seconds"] = clamp_float(normalized["source"].get("start_seconds"), 0.0, 0.0, 86400.0)
    normalized["source"]["end_seconds"] = clamp_float(normalized["source"].get("end_seconds"), 0.0, 0.0, 86400.0)
    if normalized["source"]["end_seconds"] and normalized["source"]["end_seconds"] < normalized["source"]["start_seconds"]:
        normalized["source"]["end_seconds"] = normalized["source"]["start_seconds"]

    normalized["publish"]["platforms"] = ensure_str_list(normalized["publish"].get("platforms"))
    normalized["publish"]["need_subtitles"] = coerce_bool(normalized["publish"].get("need_subtitles"), False)

    normalized["output"]["prefix"] = str(normalized["output"].get("prefix") or "processed").strip("/") or "processed"
    normalized["output"]["target_height"] = clamp_int(normalized["output"].get("target_height"), 720, 240, 2160)
    normalized["output"]["video_codec"] = str(normalized["output"].get("video_codec") or "libx264").strip() or "libx264"
    normalized["output"]["audio_codec"] = str(normalized["output"].get("audio_codec") or "aac").strip() or "aac"

    normalized["execution"]["max_retries"] = clamp_int(normalized["execution"].get("max_retries"), 2, 0, 10)
    normalized["execution"]["simulate_fail"] = coerce_bool(normalized["execution"].get("simulate_fail"), False)
    normalized["execution"]["required_capabilities"] = ensure_str_list(
        normalized["execution"].get("required_capabilities")
    )
    normalized["execution"]["preferred_worker_codes"] = ensure_str_list(
        normalized["execution"].get("preferred_worker_codes")
    )
    normalized["execution"]["lease_timeout_seconds"] = clamp_int(
        normalized["execution"].get("lease_timeout_seconds"),
        1800,
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
    rotation["min_degrees"] = clamp_float(rotation.get("min_degrees"), defaults["dedupe"]["rotation"]["min_degrees"], -3.0, 3.0)
    rotation["max_degrees"] = clamp_float(rotation.get("max_degrees"), defaults["dedupe"]["rotation"]["max_degrees"], -3.0, 3.0)
    if rotation["min_degrees"] > rotation["max_degrees"]:
        rotation["min_degrees"], rotation["max_degrees"] = rotation["max_degrees"], rotation["min_degrees"]

    color = normalized["dedupe"].setdefault("color", {})
    color["brightness_min"] = clamp_float(color.get("brightness_min"), defaults["dedupe"]["color"]["brightness_min"], 0.85, 1.15)
    color["brightness_max"] = clamp_float(color.get("brightness_max"), defaults["dedupe"]["color"]["brightness_max"], 0.85, 1.15)
    if color["brightness_min"] > color["brightness_max"]:
        color["brightness_min"], color["brightness_max"] = color["brightness_max"], color["brightness_min"]
    color["contrast_min"] = clamp_float(color.get("contrast_min"), defaults["dedupe"]["color"]["contrast_min"], -20.0, 20.0)
    color["contrast_max"] = clamp_float(color.get("contrast_max"), defaults["dedupe"]["color"]["contrast_max"], -20.0, 20.0)
    if color["contrast_min"] > color["contrast_max"]:
        color["contrast_min"], color["contrast_max"] = color["contrast_max"], color["contrast_min"]

    return normalized


def find_command(command_name: str) -> str:
    resolved = shutil.which(command_name)
    if not resolved:
        raise RuntimeError(f"找不到命令：{command_name}")
    return resolved


@dataclass
class TaskPaths:
    root_dir: Path
    raw_dir: Path
    processed_dir: Path
    output_dir: Path
    temp_dir: Path


@dataclass
class DedupePlan:
    enabled: bool
    seed: int
    profile: str
    intensity: float
    head_trim_seconds: float
    tail_trim_seconds: float
    speed_factor: float
    crop_ratio: float
    crop_x_ratio: float
    crop_y_ratio: float
    rotation_degrees: float
    mirror: bool
    brightness_factor: float
    contrast_amount: float


@dataclass
class MediaInfo:
    width: int
    height: int
    duration_seconds: float
    has_audio: bool


class WorkerClient:
    def __init__(self):
        self.api_base_url = env("API_BASE_URL").rstrip("/")
        if not self.api_base_url:
            raise RuntimeError("缺少 API_BASE_URL")

        self.worker_code = env("WORKER_CODE", "worker-cn-001")
        self.display_name = env("WORKER_DISPLAY_NAME", self.worker_code)
        self.machine_info = env("WORKER_MACHINE_INFO", "Windows Worker")
        self.capabilities = [
            item.strip()
            for item in env("WORKER_CAPABILITIES", "yt-dlp,ffmpeg,ffprobe,upload-r2,llm-agent").split(",")
            if item.strip()
        ]
        self.max_parallel_tasks = env_int("WORKER_MAX_PARALLEL_TASKS", 1, 1)
        self.scheduler_weight = env_int("WORKER_SCHEDULER_WEIGHT", 100, 1)
        self.worker_token = env("WORKER_TOKEN")
        self.idle_status = env("WORKER_IDLE_STATUS", "idle")
        self.poll_interval_seconds = env_int("WORKER_POLL_INTERVAL_SECONDS", 10, 3)
        self.heartbeat_interval_seconds = env_int("WORKER_HEARTBEAT_INTERVAL_SECONDS", 15, 5)
        self.default_simulate_seconds = env_int("WORKER_SIMULATE_SECONDS", 8, 1)
        self.default_source_type = env("WORKER_SOURCE_TYPE_DEFAULT", "youtube")
        self.root_dir = Path(env("WORKER_ROOT_DIR", "./runtime")).resolve()
        self.session = requests.Session()

    def build_headers(self, *, include_json: bool = True, require_token: bool = False) -> dict:
        headers = {}
        if include_json:
            headers["Content-Type"] = "application/json"
        if self.worker_token:
            headers["Authorization"] = f"Bearer {self.worker_token}"
        elif require_token:
            raise RuntimeError("缺少 WORKER_TOKEN，无法完成 Worker 注册或任务执行鉴权")
        return headers

    def _post(self, path: str, payload: dict, *, require_token: bool = False):
        response = self.session.post(
            f"{self.api_base_url}{path}",
            json=payload,
            headers=self.build_headers(require_token=require_token),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def register(self):
        return self._post(
            "/worker/register",
            {
                "worker_code": self.worker_code,
                "display_name": self.display_name,
                "machine_info": self.machine_info,
                "capabilities": self.capabilities,
                "max_parallel_tasks": self.max_parallel_tasks,
                "scheduler_weight": self.scheduler_weight,
                "heartbeat_note": "Worker 启动完成，已通过 Token 注册",
            },
            require_token=True,
        )

    def heartbeat(self, *, status: str, current_task_title: str = "", heartbeat_note: str = ""):
        payload = {
            "worker_code": self.worker_code,
            "display_name": self.display_name,
            "status": status,
            "machine_info": self.machine_info,
            "capabilities": self.capabilities,
            "max_parallel_tasks": self.max_parallel_tasks,
            "scheduler_weight": self.scheduler_weight,
            "current_task_title": current_task_title,
            "heartbeat_note": heartbeat_note,
        }
        return self._post("/workers/heartbeat", payload)

    def claim_task(self):
        return self._post("/worker/tasks/claim", {"worker_code": self.worker_code}, require_token=True)

    def complete_task(self, task_id: int, result: dict):
        return self._post(
            f"/worker/tasks/{task_id}/complete",
            {"worker_code": self.worker_code, "result": result},
            require_token=True,
        )

    def fail_task(self, task_id: int, error_message: str, *, retryable: bool, result: dict):
        return self._post(
            f"/worker/tasks/{task_id}/fail",
            {
                "worker_code": self.worker_code,
                "error_message": error_message,
                "retryable": retryable,
                "result": result,
            },
            require_token=True,
        )


class WorkerProcessor:
    def __init__(self, client: WorkerClient):
        self.client = client
        self.ytdlp_bin = env("YTDLP_BIN", "yt-dlp")
        self.ffmpeg_bin = env("FFMPEG_BIN", "ffmpeg")
        self.ffprobe_bin = env("FFPROBE_BIN", "ffprobe")
        self.deepseek_api_key = env("DEEPSEEK_API_KEY")
        self.deepseek_base_url = env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model = env("DEEPSEEK_MODEL", "deepseek-chat")
        self.agnes_video_api_key = env("AGNES_VIDEO_API_KEY")
        self.agnes_video_base_url = env("AGNES_VIDEO_BASE_URL", "https://apihub.agnes-ai.com/v1")
        self.agnes_video_model = env("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash")
        self.s3_bucket = env("S3_BUCKET")
        self.s3_region = env("S3_REGION", "auto")
        self.s3_endpoint = env("S3_ENDPOINT")
        self.s3_access_key = env("S3_ACCESS_KEY")
        self.s3_secret_key = env("S3_SECRET_KEY")
        self.root_dir = client.root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def require_runtime(self):
        find_command(self.ffmpeg_bin)
        find_command(self.ffprobe_bin)
        find_command(self.ytdlp_bin)
        if not all([self.s3_bucket, self.s3_endpoint, self.s3_access_key, self.s3_secret_key]):
            raise RuntimeError("缺少 R2 环境变量，请填写 S3_BUCKET / S3_ENDPOINT / S3_ACCESS_KEY / S3_SECRET_KEY")

    def make_task_paths(self, task_id: int) -> TaskPaths:
        task_root = self.root_dir / f"task-{task_id}"
        raw_dir = task_root / "raw"
        processed_dir = task_root / "processed"
        output_dir = task_root / "output"
        temp_dir = task_root / "temp"
        for directory in [raw_dir, processed_dir, output_dir, temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        return TaskPaths(task_root, raw_dir, processed_dir, output_dir, temp_dir)

    def get_payload(self, task: dict) -> dict:
        return normalize_task_payload(task.get("payload") or {})

    def get_agent_flow_input(self, task: dict) -> dict:
        payload = self.get_payload(task)
        agent_flow = payload["agent_flow"]
        return {
            "goal": agent_flow["goal"] or "选题/提示词优化/发布文案生成",
            "topic_seed": agent_flow["topic_seed"] or task.get("source_value") or task.get("title") or "",
            "platform": agent_flow["platform"],
            "audience": agent_flow["audience"],
            "tone": agent_flow["tone"],
            "language": agent_flow["language"],
            "reference_prompt": agent_flow["reference_prompt"],
            "reference_copy": agent_flow["reference_copy"],
            "source_value": task.get("source_value") or "",
            "task_title": task.get("title") or "",
        }

    def strip_json_fence(self, text: str) -> str:
        normalized = text.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()
        return normalized

    def call_deepseek_chat(self, body: dict) -> dict:
        if not self.deepseek_api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY，无法执行 agent_flow 文案工作流")

        response = self.client.session.post(
            f"{self.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=180,
        )
        response.raise_for_status()
        return response.json()

    def run_deepseek_agent_flow(self, task: dict) -> dict:
        payload = self.get_payload(task)
        config = payload["agent_flow"]["deepseek"]
        if not config.get("enabled", True):
            return {"enabled": False, "message": "DeepSeek 文案工作流已禁用"}

        agent_input = self.get_agent_flow_input(task)
        self.heartbeat(task, "正在调用 DeepSeek 生成选题与文案")
        body = {
            "model": config.get("model") or self.deepseek_model,
            "temperature": float(config.get("temperature") or 0.8),
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是短视频增长运营策划。请基于用户提供的信息，输出严格 JSON，不要输出额外说明。"
                        "JSON 字段必须包含：selected_topic、topic_options、optimized_prompt、publish_copy、video_prompt。"
                        "其中 topic_options 为数组；publish_copy 内包含 title、hook、caption、hashtags。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": agent_input["goal"],
                            "topic_seed": agent_input["topic_seed"],
                            "platform": agent_input["platform"],
                            "audience": agent_input["audience"],
                            "tone": agent_input["tone"],
                            "language": agent_input["language"],
                            "reference_prompt": agent_input["reference_prompt"],
                            "reference_copy": agent_input["reference_copy"],
                            "task_title": agent_input["task_title"],
                            "source_value": agent_input["source_value"],
                            "max_topics": int(config.get("max_topics") or 5),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        data = self.call_deepseek_chat(body)
        content = (
            (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            or "{}"
        )
        content = self.strip_json_fence(str(content))
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {
                "selected_topic": agent_input["topic_seed"],
                "topic_options": [agent_input["topic_seed"]],
                "optimized_prompt": content,
                "publish_copy": {
                    "title": agent_input["task_title"] or "AI 生成文案",
                    "hook": "",
                    "caption": content,
                    "hashtags": [],
                },
                "video_prompt": content,
            }

        publish_copy = parsed.get("publish_copy") if isinstance(parsed.get("publish_copy"), dict) else {}
        publish_copy["hashtags"] = ensure_str_list(publish_copy.get("hashtags"))
        parsed["publish_copy"] = publish_copy
        parsed["topic_options"] = ensure_str_list(parsed.get("topic_options"))
        parsed["model"] = body["model"]
        parsed["provider"] = "deepseek"
        parsed["raw_response_id"] = data.get("id") or ""
        return parsed

    def extract_agnes_video_url(self, data: dict) -> str:
        candidates = [
            data.get("video_url"),
            data.get("url"),
            ((data.get("output") or {}) if isinstance(data.get("output"), dict) else {}).get("url"),
        ]
        output = data.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, dict):
                    candidates.extend([item.get("url"), item.get("video_url")])
        data_list = data.get("data")
        if isinstance(data_list, list):
            for item in data_list:
                if isinstance(item, dict):
                    candidates.extend([item.get("url"), item.get("video_url")])
        for item in candidates:
            value = str(item or "").strip()
            if value:
                return value
        return ""

    def poll_agnes_video_task(self, task: dict, video_id: str, model_name: str, timeout_seconds: int, interval_seconds: int) -> dict:
        base_root = self.agnes_video_base_url.rstrip("/")
        if base_root.endswith("/v1"):
            base_root = base_root[:-3]
        deadline = time.monotonic() + timeout_seconds
        latest = {"video_id": video_id, "model": model_name, "status": "submitted"}
        while time.monotonic() < deadline:
            self.heartbeat(task, f"正在轮询 Agnes 视频任务 {video_id}")
            response = self.client.session.get(
                f"{base_root}/agnesapi",
                params={"video_id": video_id, "model_name": model_name},
                headers={"Authorization": f"Bearer {self.agnes_video_api_key}"},
                timeout=120,
            )
            response.raise_for_status()
            latest = response.json()
            status = str(latest.get("status") or "").lower()
            if status in {"succeeded", "success", "completed"}:
                latest["video_url"] = self.extract_agnes_video_url(latest)
                return latest
            if status in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"Agnes 视频生成失败：{json.dumps(latest, ensure_ascii=False)}")
            time.sleep(interval_seconds)

        latest["status"] = latest.get("status") or "queued"
        latest["timed_out"] = True
        return latest

    def run_agnes_video_flow(self, task: dict, video_prompt: str) -> dict:
        payload = self.get_payload(task)
        config = payload["agent_flow"]["video"]
        if not config.get("enabled"):
            return {"enabled": False, "message": "Agnes 异步视频生成未启用"}
        if not self.agnes_video_api_key:
            raise RuntimeError("缺少 AGNES_VIDEO_API_KEY，无法提交 Agnes Video 任务")

        self.heartbeat(task, "正在提交 Agnes 异步视频生成任务")
        model_name = config.get("model") or self.agnes_video_model
        request_body = {
            "model": model_name,
            "prompt": video_prompt,
            "seconds": str(config.get("seconds") or "5"),
            "size": str(config.get("size") or "1280x720"),
        }
        response = self.client.session.post(
            f"{self.agnes_video_base_url.rstrip('/')}/videos",
            headers={
                "Authorization": f"Bearer {self.agnes_video_api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=180,
        )
        response.raise_for_status()
        created = response.json()
        video_id = str(created.get("video_id") or created.get("id") or "").strip()
        result = {
            "provider": "agnes",
            "model": model_name,
            "request": request_body,
            "create_response": created,
        }
        if not video_id:
            return result

        polled = self.poll_agnes_video_task(
            task,
            video_id=video_id,
            model_name=model_name,
            timeout_seconds=clamp_int(config.get("poll_timeout_seconds"), 120, 10, 3600),
            interval_seconds=clamp_int(config.get("poll_interval_seconds"), 10, 2, 300),
        )
        result["video_id"] = video_id
        result["retrieve_response"] = polled
        result["status"] = polled.get("status") or created.get("status") or "queued"
        result["video_url"] = self.extract_agnes_video_url(polled)
        return result

    def run_agent_flow(self, task: dict) -> dict:
        payload = self.get_payload(task)
        deepseek_result = self.run_deepseek_agent_flow(task)
        video_prompt = str(
            deepseek_result.get("video_prompt")
            or deepseek_result.get("optimized_prompt")
            or self.get_agent_flow_input(task)["topic_seed"]
        ).strip()
        agnes_result = self.run_agnes_video_flow(task, video_prompt)
        return {
            "processed_by": self.client.worker_code,
            "completed_at": now_iso(),
            "workflow_type": "agent_flow",
            "task_payload": payload,
            "agent_flow": {
                "goal": payload["agent_flow"]["goal"],
                "deepseek": deepseek_result,
                "video": agnes_result,
            },
            "message": "Agent Flow 已完成选题 / 提示词优化 / 发布文案生成流程",
        }

    def get_dedupe_plan(self, task: dict, clip_width: int, clip_height: int) -> DedupePlan:
        payload = self.get_payload(task)
        dedupe = payload["dedupe"]
        if not dedupe.get("enabled", True):
            return DedupePlan(
                enabled=False,
                seed=int(task["id"]),
                profile=dedupe["profile"],
                intensity=0.0,
                head_trim_seconds=0.0,
                tail_trim_seconds=0.0,
                speed_factor=1.0,
                crop_ratio=1.0,
                crop_x_ratio=0.5,
                crop_y_ratio=0.5,
                rotation_degrees=0.0,
                mirror=False,
                brightness_factor=1.0,
                contrast_amount=0.0,
            )

        seed = int(dedupe.get("seed") or task["id"])
        rng = random.Random(seed)
        intensity = clamp_float(dedupe.get("intensity"), 0.55, 0.0, 1.0)
        randomize = dedupe.get("randomize", True)

        def choose(min_value: float, max_value: float, neutral: float) -> float:
            min_value = min(min_value, max_value)
            max_value = max(min_value, max_value)
            if not randomize:
                return (min_value + max_value) / 2.0
            if neutral >= 0:
                lower = neutral + (min_value - neutral) * intensity
                upper = neutral + (max_value - neutral) * intensity
            else:
                lower = min_value * intensity
                upper = max_value * intensity
            return rng.uniform(lower, upper)

        trim = dedupe.get("trim", {})
        speed = dedupe.get("speed", {})
        crop = dedupe.get("crop", {})
        rotation = dedupe.get("rotation", {})
        color = dedupe.get("color", {})

        crop_ratio = choose(
            clamp_float(crop.get("min_ratio"), 0.978, 0.9, 1.0),
            clamp_float(crop.get("max_ratio"), 0.994, 0.9, 1.0),
            1.0,
        )
        crop_ratio = max(0.9, min(1.0, crop_ratio))
        x_margin_ratio = max(0.0, 1.0 - crop_ratio)
        y_margin_ratio = max(0.0, 1.0 - crop_ratio)
        crop_x_ratio = 0.5 if not randomize or x_margin_ratio <= 1e-6 else rng.uniform(0.0, 1.0)
        crop_y_ratio = 0.5 if not randomize or y_margin_ratio <= 1e-6 else rng.uniform(0.0, 1.0)

        return DedupePlan(
            enabled=True,
            seed=seed,
            profile=dedupe["profile"],
            intensity=intensity,
            head_trim_seconds=clamp_float(trim.get("head_seconds"), 0.18, 0.0, 30.0),
            tail_trim_seconds=clamp_float(trim.get("tail_seconds"), 0.12, 0.0, 30.0),
            speed_factor=choose(
                clamp_float(speed.get("min_factor"), 1.01, 0.9, 1.2),
                clamp_float(speed.get("max_factor"), 1.035, 0.9, 1.2),
                1.0,
            ),
            crop_ratio=crop_ratio,
            crop_x_ratio=crop_x_ratio,
            crop_y_ratio=crop_y_ratio,
            rotation_degrees=choose(
                clamp_float(rotation.get("min_degrees"), -0.45, -3.0, 3.0),
                clamp_float(rotation.get("max_degrees"), 0.45, -3.0, 3.0),
                0.0,
            ),
            mirror=(randomize and rng.random() < clamp_float(dedupe.get("mirror_chance"), 0.15, 0.0, 1.0) * intensity),
            brightness_factor=choose(
                clamp_float(color.get("brightness_min"), 0.97, 0.85, 1.15),
                clamp_float(color.get("brightness_max"), 1.04, 0.85, 1.15),
                1.0,
            ),
            contrast_amount=choose(
                clamp_float(color.get("contrast_min"), -4.0, -20.0, 20.0),
                clamp_float(color.get("contrast_max"), 8.0, -20.0, 20.0),
                0.0,
            ),
        )

    def heartbeat(self, task: dict, note: str):
        self.client.heartbeat(
            status="running",
            current_task_title=task["title"],
            heartbeat_note=note,
        )

    def run_subprocess(self, command: list[str], task: dict, note: str):
        self.heartbeat(task, note)
        print(f"[{now_iso()}] 执行命令：{' '.join(command)}")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        heartbeat_interval = self.client.heartbeat_interval_seconds
        last_heartbeat_at = time.monotonic()
        output_lines = []

        while True:
            line = process.stdout.readline() if process.stdout else ""
            if line:
                clean_line = line.rstrip()
                output_lines.append(clean_line)
                if len(output_lines) > 40:
                    output_lines = output_lines[-40:]
                print(clean_line)

            if process.poll() is not None:
                break

            if time.monotonic() - last_heartbeat_at >= heartbeat_interval:
                self.heartbeat(task, note)
                last_heartbeat_at = time.monotonic()

        if process.returncode != 0:
            tail = "\n".join(output_lines[-10:])
            raise RuntimeError(f"{note} 失败，退出码 {process.returncode}\n{tail}")

    def probe_media_info(self, media_path: Path) -> MediaInfo:
        command = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(media_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"ffprobe 探测媒体信息失败：{completed.stderr.strip()}")

        try:
            data = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as error:
            raise RuntimeError(f"ffprobe 返回内容无法解析：{error}") from error

        streams = data.get("streams") or []
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
        if not video_stream:
            raise RuntimeError("输入文件中未找到视频流")

        width = clamp_int(video_stream.get("width"), 0, 1, 100000)
        height = clamp_int(video_stream.get("height"), 0, 1, 100000)
        duration = clamp_float(
            video_stream.get("duration") or (data.get("format") or {}).get("duration"),
            0.0,
            0.0,
            86400.0,
        )
        has_audio = any(item.get("codec_type") == "audio" for item in streams)
        return MediaInfo(
            width=width,
            height=height,
            duration_seconds=duration,
            has_audio=has_audio,
        )

    def build_atempo_filters(self, speed_factor: float) -> list[str]:
        if abs(speed_factor - 1.0) <= 1e-6:
            return []

        filters = []
        remaining = speed_factor
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.6f}")
        return filters

    def download_youtube(self, task: dict, source_url: str, paths: TaskPaths) -> Path:
        output_template = str(paths.raw_dir / "source.%(ext)s")
        ffmpeg_location = self.ffmpeg_bin
        if Path(self.ffmpeg_bin).suffix.lower() == ".exe":
            ffmpeg_location = str(Path(self.ffmpeg_bin).parent)
        command = [
            self.ytdlp_bin,
            "--no-playlist",
            "--no-update",
            "--ffmpeg-location",
            ffmpeg_location,
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            source_url,
        ]
        self.run_subprocess(command, task, "使用 yt-dlp 下载素材")

        files = sorted(paths.raw_dir.glob("source.*"))
        if not files:
            raise RuntimeError("yt-dlp 下载完成后未找到素材文件")
        return files[0]

    def download_http_file(self, task: dict, source_url: str, paths: TaskPaths) -> Path:
        parsed = urlparse(source_url)
        suffix = Path(parsed.path).suffix or ".bin"
        output_path = paths.raw_dir / f"source{suffix}"
        self.heartbeat(task, "正在下载直链素材")
        with self.client.session.get(source_url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with output_path.open("wb") as file_obj:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        file_obj.write(chunk)
        return output_path

    def resolve_source(self, task: dict, paths: TaskPaths) -> Path:
        payload = self.get_payload(task)
        source_type = (task.get("source_type") or self.client.default_source_type).lower()
        source_value = task.get("source_value") or ""

        if source_type == "youtube" or "youtube.com" in source_value.lower() or "youtu.be" in source_value.lower():
            return self.download_youtube(task, source_value, paths)

        if source_type in {"http", "https", "download", "direct_url"} or source_value.lower().startswith("http"):
            return self.download_http_file(task, source_value, paths)

        if source_type == "local_file":
            source_path = Path(source_value)
            if not source_path.exists():
                raise RuntimeError(f"本地素材不存在：{source_value}")
            target_path = paths.raw_dir / source_path.name
            shutil.copy2(source_path, target_path)
            return target_path

        if payload["source"].get("asset_key"):
            raise RuntimeError("当前版本暂未实现从 R2 回拉 asset_key，请先使用 youtube/http/local_file")

        raise RuntimeError(f"暂不支持的素材来源：{source_type}")

    def normalize_with_ffmpeg(self, task: dict, input_path: Path, paths: TaskPaths) -> Path:
        output_path = paths.processed_dir / "normalized.mp4"
        command = [
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self.run_subprocess(command, task, "使用 FFmpeg 归一化视频")
        if not output_path.exists():
            raise RuntimeError("FFmpeg 输出文件不存在")
        return output_path

    def process_with_ffmpeg(self, task: dict, input_path: Path, paths: TaskPaths) -> tuple[Path, DedupePlan]:
        payload = self.get_payload(task)
        output_path = paths.output_dir / "final.mp4"
        source_section = payload["source"]
        media_info = self.probe_media_info(input_path)
        plan = self.get_dedupe_plan(task, media_info.width, media_info.height)

        trim_start = max(0.0, float(source_section.get("start_seconds") or 0.0) + plan.head_trim_seconds)
        trim_end = max(0.0, float(source_section.get("end_seconds") or 0.0))
        end_at = trim_end if trim_end > 0 else media_info.duration_seconds
        if plan.tail_trim_seconds > 0:
            end_at = min(end_at, media_info.duration_seconds) - plan.tail_trim_seconds
        end_at = min(media_info.duration_seconds, end_at)
        if end_at <= trim_start + 0.1:
            end_at = min(media_info.duration_seconds, trim_start + 0.1)
        output_duration = max(0.1, end_at - trim_start)

        current_width = media_info.width
        current_height = media_info.height
        target_width = max(2, int(current_width * plan.crop_ratio))
        target_crop_height = max(2, int(current_height * plan.crop_ratio))
        max_x = max(0, current_width - target_width)
        max_y = max(0, current_height - target_crop_height)
        crop_x = int(max_x * plan.crop_x_ratio)
        crop_y = int(max_y * plan.crop_y_ratio)

        contrast_factor = max(0.1, 1.0 + (plan.contrast_amount / 100.0))
        brightness_shift = plan.brightness_factor - 1.0

        video_filters = []
        if target_width < current_width or target_crop_height < current_height:
            video_filters.append(f"crop={target_width}:{target_crop_height}:{crop_x}:{crop_y}")
        if plan.mirror:
            video_filters.append("hflip")
        if abs(plan.rotation_degrees) > 1e-6:
            radians = math.radians(plan.rotation_degrees)
            video_filters.append(f"rotate={radians:.8f}:fillcolor=black")
        if abs(brightness_shift) > 1e-6 or abs(contrast_factor - 1.0) > 1e-6:
            video_filters.append(f"eq=brightness={brightness_shift:.6f}:contrast={contrast_factor:.6f}")
        if abs(plan.speed_factor - 1.0) > 1e-6:
            video_filters.append(f"setpts=PTS/{plan.speed_factor:.6f}")
        video_filters.append(f"scale=-2:{int(payload['output']['target_height'])}")
        video_filters.append("format=yuv420p")

        audio_filters = self.build_atempo_filters(plan.speed_factor) if media_info.has_audio else []

        command = [
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-ss",
            f"{trim_start:.6f}",
            "-t",
            f"{output_duration:.6f}",
            "-vf",
            ",".join(video_filters),
            "-c:v",
            payload["output"]["video_codec"],
            "-preset",
            "veryfast",
            "-crf",
            "23",
        ]
        if media_info.has_audio:
            if audio_filters:
                command.extend(["-af", ",".join(audio_filters)])
            command.extend(["-c:a", payload["output"]["audio_codec"]])
        else:
            command.append("-an")
        command.extend(["-movflags", "+faststart", str(output_path)])

        self.run_subprocess(command, task, "使用 FFmpeg 去重流水线处理成片")
        if not output_path.exists():
            raise RuntimeError("FFmpeg 去重流水线输出文件不存在")
        return output_path, plan

    def create_s3_client(self):
        return boto3.client(
            "s3",
            endpoint_url=self.s3_endpoint,
            aws_access_key_id=self.s3_access_key,
            aws_secret_access_key=self.s3_secret_key,
            region_name=self.s3_region,
            config=Config(signature_version="s3v4"),
        )

    def upload_to_r2(self, task: dict, final_path: Path) -> dict:
        payload = self.get_payload(task)
        prefix = payload["output"]["prefix"]
        original_name = final_path.name
        stored_name = f"task-{task['id']}-{int(time.time())}{final_path.suffix.lower()}"
        key = f"{prefix}/{stored_name}"

        self.heartbeat(task, "正在上传结果到 R2")
        client = self.create_s3_client()
        client.upload_file(
            str(final_path),
            self.s3_bucket,
            key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        size_bytes = final_path.stat().st_size
        return {
            "source_type": "worker",
            "bucket": self.s3_bucket,
            "key": key,
            "prefix": prefix,
            "original_filename": original_name,
            "stored_filename": stored_name,
            "content_type": "video/mp4",
            "size_bytes": size_bytes,
            "storage_url": f"{self.s3_endpoint.rstrip('/')}/{self.s3_bucket}/{key}",
        }

    def run_real_pipeline(self, task: dict):
        self.require_runtime()
        paths = self.make_task_paths(task["id"])
        payload = self.get_payload(task)

        source_path = self.resolve_source(task, paths)
        normalized_path = self.normalize_with_ffmpeg(task, source_path, paths)
        final_path, dedupe_plan = self.process_with_ffmpeg(task, normalized_path, paths)
        asset = self.upload_to_r2(task, final_path)
        return {
            "processed_by": self.client.worker_code,
            "completed_at": now_iso(),
            "pipeline": {
                "source_type": task.get("source_type") or self.client.default_source_type,
                "used_yt_dlp": True,
                "used_ffmpeg": True,
                "used_ffmpeg_dedupe": True,
                "working_directory": str(paths.root_dir),
                "schema_version": payload["schema_version"],
            },
            "source": {
                "value": task.get("source_value") or "",
                "downloaded_path": str(source_path),
                "normalized_path": str(normalized_path),
                "final_path": str(final_path),
            },
            "asset": asset,
            "task_payload": payload,
            "dedupe_plan": {
                "profile": dedupe_plan.profile,
                "seed": dedupe_plan.seed,
                "intensity": dedupe_plan.intensity,
                "head_trim_seconds": dedupe_plan.head_trim_seconds,
                "tail_trim_seconds": dedupe_plan.tail_trim_seconds,
                "speed_factor": dedupe_plan.speed_factor,
                "crop_ratio": dedupe_plan.crop_ratio,
                "rotation_degrees": dedupe_plan.rotation_degrees,
                "mirror": dedupe_plan.mirror,
                "brightness_factor": dedupe_plan.brightness_factor,
                "contrast_amount": dedupe_plan.contrast_amount,
            },
            "message": "Worker 已完成真实拉素材 / FFmpeg 归一化 / FFmpeg 去重流水线 / R2 上传流程",
        }


def should_simulate_failure(task: dict) -> bool:
    payload = normalize_task_payload(task.get("payload") or {})
    source_value = (task.get("source_value") or "").lower()
    title = (task.get("title") or "").lower()
    return bool(payload["execution"].get("simulate_fail")) or "fail-demo" in source_value or "fail-demo" in title


def main():
    try:
        client = WorkerClient()
        processor = WorkerProcessor(client)
    except Exception as error:
        print(f"初始化 Worker 失败：{error}")
        sys.exit(1)

    print(f"[{now_iso()}] Worker 启动：{client.display_name} ({client.worker_code})")
    try:
        register_response = client.register()
        print(f"[{now_iso()}] Worker 注册成功：{json.dumps(register_response, ensure_ascii=False)}")
    except Exception as error:
        print(f"[{now_iso()}] Worker 注册失败：{error}")
        sys.exit(1)

    while True:
        try:
            client.heartbeat(
                status=client.idle_status,
                current_task_title="",
                heartbeat_note="心跳正常，准备领取任务",
            )
            claimed = client.claim_task()
            task = claimed.get("item")
            if not task:
                print(f"[{now_iso()}] 暂无任务，{client.poll_interval_seconds} 秒后重试")
                time.sleep(client.poll_interval_seconds)
                continue

            print(f"[{now_iso()}] 已领取任务 #{task['id']}: {task['title']}")
            if should_simulate_failure(task):
                response = client.fail_task(
                    task["id"],
                    error_message="任务标记为模拟失败",
                    retryable=True,
                    result={
                        "processed_by": client.worker_code,
                        "failed_at": now_iso(),
                        "message": "命中 simulate_fail/fail-demo",
                    },
                )
                print(f"[{now_iso()}] 任务 #{task['id']} 失败：{json.dumps(response, ensure_ascii=False)}")
                time.sleep(client.poll_interval_seconds)
                continue

            task_type = str(task.get("task_type") or "").strip().lower()
            if task_type == "agent_flow":
                result = processor.run_agent_flow(task)
            else:
                result = processor.run_real_pipeline(task)
            response = client.complete_task(task["id"], result)
            print(f"[{now_iso()}] 任务 #{task['id']} 完成：{json.dumps(response, ensure_ascii=False)}")
            client.heartbeat(
                status=client.idle_status,
                current_task_title="",
                heartbeat_note="任务执行结束，等待下一次领取",
            )
        except KeyboardInterrupt:
            print("Worker 已手动停止")
            break
        except Exception as error:
            print(f"[{now_iso()}] Worker 运行异常：{error}")
            try:
                if "task" in locals() and isinstance(task, dict) and task.get("id"):
                    client.fail_task(
                        task["id"],
                        error_message=str(error),
                        retryable=True,
                        result={
                            "processed_by": client.worker_code,
                            "failed_at": now_iso(),
                            "message": "真实流程执行异常",
                        },
                    )
                client.heartbeat(
                    status="offline",
                    current_task_title="",
                    heartbeat_note=f"异常：{error}",
                )
            except Exception:
                pass
            time.sleep(client.poll_interval_seconds)


if __name__ == "__main__":
    main()
