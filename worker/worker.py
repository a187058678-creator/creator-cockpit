import json
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

try:
    from moviepy import VideoFileClip, vfx
except ImportError:  # pragma: no cover
    VideoFileClip = None
    vfx = None


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
            for item in env("WORKER_CAPABILITIES", "yt-dlp,ffmpeg,moviepy,upload-r2").split(",")
            if item.strip()
        ]
        self.idle_status = env("WORKER_IDLE_STATUS", "idle")
        self.poll_interval_seconds = env_int("WORKER_POLL_INTERVAL_SECONDS", 10, 3)
        self.heartbeat_interval_seconds = env_int("WORKER_HEARTBEAT_INTERVAL_SECONDS", 15, 5)
        self.default_simulate_seconds = env_int("WORKER_SIMULATE_SECONDS", 8, 1)
        self.default_source_type = env("WORKER_SOURCE_TYPE_DEFAULT", "youtube")
        self.root_dir = Path(env("WORKER_ROOT_DIR", "./runtime")).resolve()
        self.session = requests.Session()

    def _post(self, path: str, payload: dict):
        response = self.session.post(f"{self.api_base_url}{path}", json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    def heartbeat(self, *, status: str, current_task_title: str = "", heartbeat_note: str = ""):
        payload = {
            "worker_code": self.worker_code,
            "display_name": self.display_name,
            "status": status,
            "machine_info": self.machine_info,
            "capabilities": self.capabilities,
            "current_task_title": current_task_title,
            "heartbeat_note": heartbeat_note,
        }
        return self._post("/workers/heartbeat", payload)

    def claim_task(self):
        return self._post("/worker/tasks/claim", {"worker_code": self.worker_code})

    def complete_task(self, task_id: int, result: dict):
        return self._post(
            f"/worker/tasks/{task_id}/complete",
            {"worker_code": self.worker_code, "result": result},
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
        )


class WorkerProcessor:
    def __init__(self, client: WorkerClient):
        self.client = client
        self.ytdlp_bin = env("YTDLP_BIN", "yt-dlp")
        self.ffmpeg_bin = env("FFMPEG_BIN", "ffmpeg")
        self.s3_bucket = env("S3_BUCKET")
        self.s3_region = env("S3_REGION", "auto")
        self.s3_endpoint = env("S3_ENDPOINT")
        self.s3_access_key = env("S3_ACCESS_KEY")
        self.s3_secret_key = env("S3_SECRET_KEY")
        self.root_dir = client.root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def require_runtime(self):
        find_command(self.ffmpeg_bin)
        find_command(self.ytdlp_bin)
        if VideoFileClip is None or vfx is None:
            raise RuntimeError("MoviePy 未安装，请先执行 pip install -r worker/requirements.txt")
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

    def download_youtube(self, task: dict, source_url: str, paths: TaskPaths) -> Path:
        output_template = str(paths.raw_dir / "source.%(ext)s")
        command = [
            self.ytdlp_bin,
            "--no-playlist",
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

    def process_with_moviepy(self, task: dict, input_path: Path, paths: TaskPaths) -> Path:
        payload = self.get_payload(task)
        output_path = paths.output_dir / "final.mp4"
        target_height = int(payload["output"]["target_height"])
        source_section = payload["source"]

        self.heartbeat(task, "使用 MoviePy 精修成片")
        clip = VideoFileClip(str(input_path))
        try:
            processed = clip
            duration = float(clip.duration or 0)
            plan = self.get_dedupe_plan(
                task,
                int(getattr(clip, "w", 0) or 0),
                int(getattr(clip, "h", 0) or 0),
            )

            trim_start = max(
                0.0,
                float(source_section.get("start_seconds") or 0.0) + plan.head_trim_seconds,
            )
            trim_end = max(
                0.0,
                float(source_section.get("end_seconds") or 0.0),
            )
            end_at = trim_end if trim_end > 0 else duration
            if plan.tail_trim_seconds > 0:
                end_at = min(end_at, duration) - plan.tail_trim_seconds
            end_at = min(duration, end_at)
            if end_at <= trim_start + 0.1:
                end_at = min(duration, trim_start + 0.1)
            if trim_start > 0 or end_at < duration:
                processed = processed.subclipped(trim_start, end_at)

            effects = []
            if plan.mirror and hasattr(vfx, "MirrorX"):
                effects.append(vfx.MirrorX())
            if abs(plan.speed_factor - 1.0) > 1e-6 and hasattr(vfx, "MultiplySpeed"):
                effects.append(vfx.MultiplySpeed(plan.speed_factor))

            if plan.crop_ratio < 0.999 and hasattr(vfx, "Crop"):
                current_width = int(getattr(processed, "w", clip.w) or clip.w)
                current_height = int(getattr(processed, "h", clip.h) or clip.h)
                target_width = max(2, int(current_width * plan.crop_ratio))
                target_crop_height = max(2, int(current_height * plan.crop_ratio))
                max_x = max(0, current_width - target_width)
                max_y = max(0, current_height - target_crop_height)
                x1 = int(max_x * plan.crop_x_ratio)
                y1 = int(max_y * plan.crop_y_ratio)
                effects.append(vfx.Crop(x1=x1, y1=y1, x2=x1 + target_width, y2=y1 + target_crop_height))

            if abs(plan.rotation_degrees) > 1e-6 and hasattr(vfx, "Rotate"):
                effects.append(vfx.Rotate(plan.rotation_degrees))
            if abs(plan.brightness_factor - 1.0) > 1e-6 and hasattr(vfx, "MultiplyColor"):
                effects.append(vfx.MultiplyColor(plan.brightness_factor))
            if abs(plan.contrast_amount) > 1e-6 and hasattr(vfx, "LumContrast"):
                effects.append(vfx.LumContrast(contrast=plan.contrast_amount))

            if effects:
                processed = processed.with_effects(effects)

            if target_height:
                processed = processed.resized(height=target_height)

            processed.write_videofile(
                str(output_path),
                codec=payload["output"]["video_codec"],
                audio_codec=payload["output"]["audio_codec"],
                fps=processed.fps or 30,
                logger=None,
            )
        finally:
            if 'processed' in locals() and processed is not clip:
                processed.close()
            clip.close()

        if not output_path.exists():
            raise RuntimeError("MoviePy 输出文件不存在")
        return output_path

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
        final_path = self.process_with_moviepy(task, normalized_path, paths)
        asset = self.upload_to_r2(task, final_path)
        inspect_clip = VideoFileClip(str(normalized_path))
        try:
            dedupe_plan = self.get_dedupe_plan(
                task,
                int(getattr(inspect_clip, "w", 0) or 0),
                int(getattr(inspect_clip, "h", 0) or 0),
            )
        finally:
            inspect_clip.close()
        return {
            "processed_by": self.client.worker_code,
            "completed_at": now_iso(),
            "pipeline": {
                "source_type": task.get("source_type") or self.client.default_source_type,
                "used_yt_dlp": True,
                "used_ffmpeg": True,
                "used_moviepy": True,
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
            "message": "Worker 已完成真实拉素材 / FFmpeg / MoviePy 去重流水线 / R2 上传流程",
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
