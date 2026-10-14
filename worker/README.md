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

## 正式任务 payload（creator-task/v1）

```json
{
  "schema_version": "creator-task/v1",
  "source": {
    "asset_key": "",
    "start_seconds": 0,
    "end_seconds": 0
  },
  "publish": {
    "platforms": ["tiktok"],
    "need_subtitles": true
  },
  "output": {
    "prefix": "processed",
    "target_height": 720,
    "video_codec": "libx264",
    "audio_codec": "aac"
  },
  "execution": {
    "max_retries": 2,
    "simulate_fail": false
  },
  "dedupe": {
    "enabled": true,
    "profile": "balanced",
    "intensity": 0.55,
    "seed": 0,
    "randomize": true,
    "trim": {
      "head_seconds": 0.18,
      "tail_seconds": 0.12
    },
    "speed": {
      "min_factor": 1.01,
      "max_factor": 1.035
    },
    "crop": {
      "min_ratio": 0.978,
      "max_ratio": 0.994
    },
    "rotation": {
      "min_degrees": -0.45,
      "max_degrees": 0.45
    },
    "mirror_chance": 0.15,
    "color": {
      "brightness_min": 0.97,
      "brightness_max": 1.04,
      "contrast_min": -4,
      "contrast_max": 8
    }
  }
}
```

### 去重流水线说明

- `profile`：`light / balanced / aggressive`
- `intensity`：0 到 1，控制随机扰动强度
- `seed`：`0` 表示默认用任务 ID；固定非 0 值可复现同一套扰动
- `trim / speed / crop / rotation / mirror_chance / color`：共同组成 MoviePy 去重流水线
- 旧版扁平字段（如 `speed_factor`、`trim_start_seconds`、`output_prefix`）仍兼容，但创建任务时会被归一化成 `creator-task/v1`

## 模拟失败开关

创建任务时，如果满足以下任一条件，Worker 会走失败回写：

- `payload.execution.simulate_fail = true`
- `title` 或 `source_value` 包含 `fail-demo`
