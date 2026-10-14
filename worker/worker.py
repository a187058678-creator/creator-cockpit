import json
import os
import sys
import time
from datetime import datetime, timezone

import requests


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


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
        self.poll_interval_seconds = max(3, int(env("WORKER_POLL_INTERVAL_SECONDS", "10")))
        self.heartbeat_interval_seconds = max(5, int(env("WORKER_HEARTBEAT_INTERVAL_SECONDS", "15")))
        self.default_simulate_seconds = max(1, int(env("WORKER_SIMULATE_SECONDS", "8")))
        self.session = requests.Session()

    def _post(self, path: str, payload: dict):
        response = self.session.post(f"{self.api_base_url}{path}", json=payload, timeout=30)
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


def should_simulate_failure(task: dict) -> bool:
    payload = task.get("payload") or {}
    source_value = (task.get("source_value") or "").lower()
    title = (task.get("title") or "").lower()
    return bool(payload.get("simulate_fail")) or "fail-demo" in source_value or "fail-demo" in title


def get_simulate_seconds(task: dict, fallback: int) -> int:
    payload = task.get("payload") or {}
    raw_value = payload.get("simulate_seconds", fallback)
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return fallback


def process_task(client: WorkerClient, task: dict):
    task_id = task["id"]
    title = task["title"]
    simulate_seconds = get_simulate_seconds(task, client.default_simulate_seconds)
    print(f"[{now_iso()}] 已领取任务 #{task_id}: {title}")

    elapsed = 0
    while elapsed < simulate_seconds:
        time.sleep(1)
        elapsed += 1
        if elapsed % client.heartbeat_interval_seconds == 0 or elapsed == simulate_seconds:
            client.heartbeat(
                status="running",
                current_task_title=title,
                heartbeat_note=f"执行中 {elapsed}/{simulate_seconds} 秒",
            )

    if should_simulate_failure(task):
        response = client.fail_task(
            task_id,
            error_message="模拟执行失败：命中 fail-demo 或 simulate_fail",
            retryable=True,
            result={
                "processed_by": client.worker_code,
                "failed_at": now_iso(),
                "simulate_seconds": simulate_seconds,
            },
        )
        print(f"[{now_iso()}] 任务 #{task_id} 执行失败，结果：{json.dumps(response, ensure_ascii=False)}")
        return

    response = client.complete_task(
        task_id,
        {
            "processed_by": client.worker_code,
            "completed_at": now_iso(),
            "simulate_seconds": simulate_seconds,
            "message": "Worker 已完成模拟处理",
        },
    )
    print(f"[{now_iso()}] 任务 #{task_id} 执行成功，结果：{json.dumps(response, ensure_ascii=False)}")


def main():
    try:
        client = WorkerClient()
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

            process_task(client, task)
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
