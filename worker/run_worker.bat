@echo off
setlocal

set API_BASE_URL=https://focused-ambition-production-66f5.up.railway.app
set WORKER_CODE=worker-cn-001
set WORKER_DISPLAY_NAME=深圳一号机
set WORKER_MACHINE_INFO=Windows 11 / RTX 4060 / Clash
set WORKER_CAPABILITIES=yt-dlp,ffmpeg,ffprobe,upload-r2
set WORKER_IDLE_STATUS=idle
set WORKER_POLL_INTERVAL_SECONDS=10
set WORKER_HEARTBEAT_INTERVAL_SECONDS=5
set WORKER_ROOT_DIR=%~dp0runtime
set WORKER_SOURCE_TYPE_DEFAULT=youtube
set YTDLP_BIN=yt-dlp
set FFMPEG_BIN=ffmpeg
set FFPROBE_BIN=ffprobe
set S3_BUCKET=creator-cockpit
set S3_REGION=auto
set S3_ENDPOINT=https://your-account-id.r2.cloudflarestorage.com
set S3_ACCESS_KEY=
set S3_SECRET_KEY=

py -3 "%~dp0worker.py"
pause
