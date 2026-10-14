import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import boto3
import requests
from botocore.client import Config

try:
    from moviepy import VideoFileClip, vfx
except ImportError:  # pragma: no cover
    VideoFileClip = None
    vfx = None


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
        payload = task.get("payload") or {}
        return payload if isinstance(payload, dict) else {}

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

        if payload.get("asset_key"):
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

        trim_start = max(0.0, float(payload.get("trim_start_seconds", 0)))
        trim_end = max(0.0, float(payload.get("trim_end_seconds", 0)))
        speed_factor = env_float("WORKER_MOVIEPY_SPEED_FACTOR", float(payload.get("speed_factor", 1.0)))
        target_height = payload.get("target_height")

        self.heartbeat(task, "使用 MoviePy 精修成片")
        clip = VideoFileClip(str(input_path))
        try:
            processed = clip
            duration = float(clip.duration or 0)
            if trim_start > 0 or trim_end > 0:
                end_at = duration - trim_end if trim_end > 0 else duration
                end_at = max(trim_start + 0.1, end_at)
                processed = processed.subclipped(trim_start, end_at)

            if abs(speed_factor - 1.0) > 1e-6:
                processed = processed.with_effects([vfx.MultiplySpeed(speed_factor)])

            if target_height:
                processed = processed.resized(height=int(target_height))

            processed.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                fps=processed.fps or 30,
                logger=None,
            )
        finally:
            clip.close()
            if 'processed' in locals() and processed is not clip:
                processed.close()

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
        prefix = (payload.get("output_prefix") or "processed").strip("/") or "processed"
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

        source_path = self.resolve_source(task, paths)
        normalized_path = self.normalize_with_ffmpeg(task, source_path, paths)
        final_path = self.process_with_moviepy(task, normalized_path, paths)
        asset = self.upload_to_r2(task, final_path)

        payload = self.get_payload(task)
        return {
            "processed_by": self.client.worker_code,
            "completed_at": now_iso(),
            "pipeline": {
                "source_type": task.get("source_type") or self.client.default_source_type,
                "used_yt_dlp": True,
                "used_ffmpeg": True,
                "used_moviepy": True,
                "working_directory": str(paths.root_dir),
            },
            "source": {
                "value": task.get("source_value") or "",
                "downloaded_path": str(source_path),
                "normalized_path": str(normalized_path),
                "final_path": str(final_path),
            },
            "asset": asset,
            "task_payload": payload,
            "message": "Worker 已完成真实拉素材 / FFmpeg / MoviePy / R2 上传流程",
        }


def should_simulate_failure(task: dict) -> bool:
    payload = task.get("payload") or {}
    source_value = (task.get("source_value") or "").lower()
    title = (task.get("title") or "").lower()
    return bool(payload.get("simulate_fail")) or "fail-demo" in source_value or "fail-demo" in title


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
