# Worker

本目录用于本地 Windows Worker 验证。

## 快速启动

1. 安装依赖：
   `py -3 -m pip install -r requirements.txt`
2. 修改 `run_worker.bat` 里的 `API_BASE_URL` 和 Worker 标识。
3. 双击运行 `run_worker.bat`。

## 支持的接口

- Worker 心跳：`POST /workers/heartbeat`
- 领取任务：`POST /worker/tasks/claim`
- 完成回写：`POST /worker/tasks/{id}/complete`
- 失败回写：`POST /worker/tasks/{id}/fail`

## 模拟失败

创建任务时，如果满足以下任一条件，Worker 会走失败回写：

- `payload.simulate_fail = true`
- `title` 或 `source_value` 包含 `fail-demo`
