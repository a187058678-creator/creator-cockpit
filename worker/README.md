# Worker

本目录用于本地 Windows Worker 验证，当前版本已经接入真实流程：

- 拉素材：`yt-dlp` 或 HTTP 直链
- 归一化：`ffmpeg`
- 精修输出：`MoviePy 2.x`
- 上传结果：直传 Cloudflare R2
- 任务回写：完成 / 失败 / 重试

## 快速启动

1. 安装依赖：
   `py -3 -m pip install -r requirements.txt`
2. 安装本地工具：
   - `yt-dlp`
   - `ffmpeg`
   - `MoviePy 2.x`（已在 `requirements.txt` 中）
3. 修改 `run_worker.bat`：
   - `API_BASE_URL`
   - `S3_BUCKET / S3_ENDPOINT / S3_ACCESS_KEY / S3_SECRET_KEY`
   - Worker 标识
4. 双击运行 `run_worker.bat`。

## 支持的接口

- Worker 心跳：`POST /workers/heartbeat`
- 领取任务：`POST /worker/tasks/claim`
- 完成回写：`POST /worker/tasks/{id}/complete`
- 失败回写：`POST /worker/tasks/{id}/fail`

## 支持的任务来源

- `source_type = youtube`：`source_value` 填 YouTube 链接
- `source_type = http / https / download / direct_url`：`source_value` 填素材直链
- `source_type = local_file`：`source_value` 填本地绝对路径

## 推荐任务 payload

```json
{
  "platforms": ["tiktok"],
  "need_subtitles": true,
  "output_prefix": "processed",
  "trim_start_seconds": 0,
  "trim_end_seconds": 0,
  "speed_factor": 1.02,
  "target_height": 720,
  "max_retries": 2
}
```

## 模拟失败开关

创建任务时，如果满足以下任一条件，Worker 会走失败回写：

- `payload.simulate_fail = true`
- `title` 或 `source_value` 包含 `fail-demo`
