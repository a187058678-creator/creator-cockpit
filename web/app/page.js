"use client";

import { useEffect, useState } from "react";

const cardStyle = {
  background: "#121933",
  border: "1px solid #26314f",
  borderRadius: 14,
  padding: 16,
};

const inputStyle = {
  width: "100%",
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 10,
  color: "#e5e7eb",
  padding: "10px 12px",
  fontSize: 14,
  boxSizing: "border-box",
};

const buttonStyle = {
  background: "#4f46e5",
  color: "#fff",
  border: 0,
  borderRadius: 10,
  padding: "10px 14px",
  fontSize: 14,
  cursor: "pointer",
};

const secondaryButtonStyle = {
  ...buttonStyle,
  background: "#18213f",
  border: "1px solid #334155",
};

const taskStatusOptions = ["pending", "queued", "running", "success", "failed", "cancelled"];

function formatDate(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

async function readJson(response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

function StatusPill({ ok, text }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 999,
        fontSize: 12,
        background: ok ? "rgba(34,197,94,.14)" : "rgba(239,68,68,.14)",
        color: ok ? "#86efac" : "#fca5a5",
        border: `1px solid ${ok ? "rgba(34,197,94,.3)" : "rgba(239,68,68,.3)"}`,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 999,
          background: ok ? "#22c55e" : "#ef4444",
        }}
      />
      {text}
    </span>
  );
}

function Section({ id, title, hint, action, children }) {
  return (
    <section id={id} style={cardStyle}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
          {hint ? (
            <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>{hint}</div>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function SummaryCard({ label, value, hint, ok = true }) {
  return (
    <div style={{ ...cardStyle, padding: 14 }}>
      <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 10 }}>{value}</div>
      <StatusPill ok={ok} text={hint} />
    </div>
  );
}

export default function HomePage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "未配置";

  const [health, setHealth] = useState({ loading: true, ok: false, detail: "" });
  const [summary, setSummary] = useState({
    total_asset_records: 0,
    pending_tasks: 0,
    online_workers: 0,
    bucket: "",
    latest_asset_record: null,
    latest_task: null,
    latest_worker: null,
    storage_configured: false,
    database_configured: false,
  });
  const [taskSummary, setTaskSummary] = useState({
    total: 0,
    pending: 0,
    running: 0,
    success: 0,
    failed: 0,
    latest: null,
  });
  const [workerSummary, setWorkerSummary] = useState({
    total: 0,
    online: 0,
    offline: 0,
    latest: null,
  });
  const [assets, setAssets] = useState([]);
  const [records, setRecords] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [taskDrafts, setTaskDrafts] = useState({});
  const [taskFilter, setTaskFilter] = useState("");
  const [listPrefix, setListPrefix] = useState("assets");
  const [textPrefix, setTextPrefix] = useState("assets");
  const [textFilename, setTextFilename] = useState("");
  const [textBody, setTextBody] = useState("hello from creator cockpit");
  const [filePrefix, setFilePrefix] = useState("assets");
  const [selectedFile, setSelectedFile] = useState(null);
  const [taskForm, setTaskForm] = useState({
    title: "YouTube 采集 + 上传 TikTok",
    task_type: "publish",
    source_type: "youtube",
    source_value: "https://www.youtube.com/watch?v=demo",
    priority: "high",
    payload: '{\n  "platforms": ["tiktok"],\n  "need_subtitles": true\n}',
  });
  const [workerForm, setWorkerForm] = useState({
    worker_code: "worker-cn-001",
    display_name: "深圳一号机",
    status: "idle",
    machine_info: "Windows 11 / RTX 4060 / Clash",
    capabilities: "yt-dlp,ffmpeg,moviepy,upload-r2",
    current_task_title: "",
    heartbeat_note: "已连接 API，等待拉取任务",
  });
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");

  async function loadHealth() {
    setHealth({ loading: true, ok: false, detail: "" });
    try {
      const data = await readJson(await fetch("/api/health", { cache: "no-store" }));
      setHealth({
        loading: false,
        ok: !!data.ok,
        detail: data.detail || JSON.stringify(data),
      });
    } catch (error) {
      setHealth({ loading: false, ok: false, detail: error.message || "请求失败" });
    }
  }

  async function loadSummary() {
    try {
      const data = await readJson(await fetch("/api/dashboard/summary", { cache: "no-store" }));
      setSummary(data);
    } catch (error) {
      setMessage(error.message || "获取系统摘要失败");
    }
  }

  async function loadTaskSummary() {
    try {
      const data = await readJson(await fetch("/api/tasks/summary", { cache: "no-store" }));
      setTaskSummary(data);
    } catch (error) {
      setMessage(error.message || "获取任务摘要失败");
    }
  }

  async function loadWorkerSummary() {
    try {
      const data = await readJson(await fetch("/api/workers/summary", { cache: "no-store" }));
      setWorkerSummary(data);
    } catch (error) {
      setMessage(error.message || "获取 Worker 摘要失败");
    }
  }

  async function loadTasks(status = taskFilter) {
    try {
      const data = await readJson(
        await fetch(`/api/tasks?status=${encodeURIComponent(status)}`, { cache: "no-store" })
      );
      setTasks(data.items || []);
    } catch (error) {
      setTasks([]);
      setMessage(error.message || "获取任务列表失败");
    }
  }

  async function loadWorkers() {
    try {
      const data = await readJson(await fetch("/api/workers", { cache: "no-store" }));
      setWorkers(data.items || []);
    } catch (error) {
      setWorkers([]);
      setMessage(error.message || "获取 Worker 列表失败");
    }
  }

  async function loadAssets(prefix = listPrefix) {
    try {
      const data = await readJson(
        await fetch(`/api/assets/list?prefix=${encodeURIComponent(prefix)}`, { cache: "no-store" })
      );
      setAssets(data.items || []);
    } catch (error) {
      setAssets([]);
      setMessage(error.message || "获取资产失败");
    }
  }

  async function loadRecords(prefix = listPrefix) {
    try {
      const data = await readJson(
        await fetch(`/api/assets/records?prefix=${encodeURIComponent(prefix)}`, {
          cache: "no-store",
        })
      );
      setRecords(data.items || []);
    } catch (error) {
      setRecords([]);
      setMessage(error.message || "获取数据库记录失败");
    }
  }

  async function reloadAll() {
    await Promise.all([
      loadHealth(),
      loadSummary(),
      loadTaskSummary(),
      loadWorkerSummary(),
      loadTasks(taskFilter),
      loadWorkers(),
      loadAssets(listPrefix),
      loadRecords(listPrefix),
    ]);
  }

  useEffect(() => {
    reloadAll();
  }, []);

  async function uploadText(event) {
    event.preventDefault();
    setBusy("text");
    setMessage("正在上传文本...");
    try {
      const data = await readJson(
        await fetch("/api/assets/text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: textBody,
            prefix: textPrefix,
            filename: textFilename || undefined,
          }),
        })
      );
      setMessage(`文本上传成功：${data.key}`);
      setListPrefix(textPrefix);
      await Promise.all([loadAssets(textPrefix), loadRecords(textPrefix), loadSummary()]);
    } catch (error) {
      setMessage(error.message || "文本上传失败");
    } finally {
      setBusy("");
    }
  }

  async function uploadFile(event) {
    event.preventDefault();
    if (!selectedFile) {
      setMessage("请先选择文件");
      return;
    }

    setBusy("file");
    setMessage("正在上传文件...");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const data = await readJson(
        await fetch(`/api/assets/file?prefix=${encodeURIComponent(filePrefix)}`, {
          method: "POST",
          body: formData,
        })
      );
      setMessage(`文件上传成功：${data.key}`);
      setSelectedFile(null);
      setListPrefix(filePrefix);
      await Promise.all([loadAssets(filePrefix), loadRecords(filePrefix), loadSummary()]);
    } catch (error) {
      setMessage(error.message || "文件上传失败");
    } finally {
      setBusy("");
    }
  }

  async function createTask(event) {
    event.preventDefault();
    setBusy("task");
    setMessage("正在创建任务...");
    try {
      const data = await readJson(
        await fetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...taskForm,
            payload: JSON.parse(taskForm.payload || "{}"),
          }),
        })
      );
      setMessage(`任务已创建：#${data.item.id} ${data.item.title}`);
      await Promise.all([loadTasks(taskFilter), loadTaskSummary(), loadSummary()]);
    } catch (error) {
      setMessage(error.message || "创建任务失败");
    } finally {
      setBusy("");
    }
  }

  function updateTaskDraft(taskId, field, value) {
    setTaskDrafts((prev) => ({
      ...prev,
      [taskId]: {
        ...(prev[taskId] || {}),
        [field]: value,
      },
    }));
  }

  async function saveTaskUpdate(task) {
    const draft = taskDrafts[task.id] || {};
    const nextStatus = draft.status ?? task.status;
    const nextWorkerCode = draft.assigned_worker_code ?? task.assigned_worker_code ?? "";

    setBusy(`task-${task.id}`);
    setMessage(`正在保存任务 #${task.id}...`);
    try {
      const data = await readJson(
        await fetch(`/api/tasks/${task.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: nextStatus,
            assigned_worker_code: nextWorkerCode,
          }),
        })
      );
      setMessage(`任务已更新：#${data.item.id} -> ${data.item.status}`);
      setTaskDrafts((prev) => {
        const next = { ...prev };
        delete next[task.id];
        return next;
      });
      await Promise.all([
        loadTasks(taskFilter),
        loadTaskSummary(),
        loadWorkerSummary(),
        loadWorkers(),
        loadSummary(),
      ]);
    } catch (error) {
      setMessage(error.message || "更新任务失败");
    } finally {
      setBusy("");
    }
  }

  async function retryTask(taskId) {
    setBusy(`retry-${taskId}`);
    setMessage(`正在重试任务 #${taskId}...`);
    try {
      const data = await readJson(
        await fetch(`/api/tasks/${taskId}/retry`, {
          method: "POST",
        })
      );
      setMessage(`任务已重试入队：#${data.item.id}`);
      await Promise.all([
        loadTasks(taskFilter),
        loadTaskSummary(),
        loadWorkerSummary(),
        loadWorkers(),
        loadSummary(),
      ]);
    } catch (error) {
      setMessage(error.message || "任务重试失败");
    } finally {
      setBusy("");
    }
  }

  async function submitHeartbeat(event) {
    event.preventDefault();
    setBusy("worker");
    setMessage("正在登记 Worker...");
    try {
      const data = await readJson(
        await fetch("/api/workers/heartbeat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...workerForm,
            capabilities: workerForm.capabilities
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
          }),
        })
      );
      setMessage(`Worker 已更新：${data.item.display_name}`);
      await Promise.all([loadWorkers(), loadWorkerSummary(), loadSummary()]);
    } catch (error) {
      setMessage(error.message || "提交 Worker 心跳失败");
    } finally {
      setBusy("");
    }
  }

  async function createPreviewLink(key) {
    setBusy(`preview-${key}`);
    try {
      const data = await readJson(await fetch(`/api/assets/presign?key=${encodeURIComponent(key)}`));
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (error) {
      setMessage(error.message || "生成预览链接失败");
    } finally {
      setBusy("");
    }
  }

  const summaryCards = [
    {
      label: "服务状态",
      value: health.loading ? "检查中" : health.ok ? "正常" : "异常",
      hint: "API 健康检查",
      ok: health.ok,
    },
    {
      label: "待处理任务",
      value: String(taskSummary.pending || 0),
      hint: "还没被 Worker 领取",
      ok: (taskSummary.pending || 0) > 0,
    },
    {
      label: "在线 Worker",
      value: String(workerSummary.online || 0),
      hint: "可领取任务的节点",
      ok: (workerSummary.online || 0) > 0,
    },
    {
      label: "资产记录",
      value: String(summary.total_asset_records || 0),
      hint: summary.bucket || "R2 / 数据库",
      ok: summary.storage_configured,
    },
  ];

  return (
    <main style={{ maxWidth: 1440, margin: "0 auto", padding: 20 }}>
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 360px)",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 34 }}>Creator Cockpit</h1>
          <div style={{ marginTop: 8, color: "#94a3b8", fontSize: 14 }}>
            先看系统活没活，再建任务、看 Worker、最后查文件和记录。
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
            <a href="#overview" style={{ ...secondaryButtonStyle, textDecoration: "none" }}>运行状态</a>
            <a href="#tasks" style={{ ...secondaryButtonStyle, textDecoration: "none" }}>创建任务</a>
            <a href="#workers" style={{ ...secondaryButtonStyle, textDecoration: "none" }}>Worker 节点</a>
            <a href="#storage" style={{ ...secondaryButtonStyle, textDecoration: "none" }}>文件与记录</a>
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>当前 API 地址</div>
          <div style={{ fontSize: 13, wordBreak: "break-all" }}>{apiBaseUrl}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button type="button" style={buttonStyle} onClick={reloadAll}>
              刷新全部
            </button>
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={() => window.open("/api/dashboard/summary", "_blank", "noopener,noreferrer")}
            >
              看摘要 JSON
            </button>
          </div>
        </div>
      </section>

      <section
        id="overview"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 16,
          marginBottom: 16,
        }}
      >
        {summaryCards.map((item) => (
          <SummaryCard
            key={item.label}
            label={item.label}
            value={item.value}
            hint={item.hint}
            ok={item.ok}
          />
        ))}
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <Section title="现在最重要的事" hint="如果你只想知道项目现在卡在哪，就看这里。">
          <div style={{ display: "grid", gap: 10, fontSize: 14, color: "#cbd5e1" }}>
            <div>API：{health.ok ? "能通" : `异常 - ${health.detail || "待检查"}`}</div>
            <div>数据库：{summary.database_configured ? "已接入" : "未接入"}</div>
            <div>R2：{summary.storage_configured ? `已接入（${summary.bucket || "未命名"}）` : "未接入"}</div>
            <div>最新任务：{summary.latest_task?.title || "还没有任务"}</div>
            <div>最新 Worker：{summary.latest_worker?.display_name || "还没有节点"}</div>
          </div>
        </Section>

        <Section title="任务概况" hint="一眼看清任务队列，不用翻大表。">
          <div style={{ display: "grid", gap: 10, fontSize: 14, color: "#cbd5e1" }}>
            <div>总任务：{taskSummary.total || 0}</div>
            <div>待处理：{taskSummary.pending || 0}</div>
            <div>运行中：{taskSummary.running || 0}</div>
            <div>成功：{taskSummary.success || 0}</div>
            <div>失败：{taskSummary.failed || 0}</div>
          </div>
        </Section>

        <Section title="Worker 概况" hint="先看在线数量，再看有没有节点超时。">
          <div style={{ display: "grid", gap: 10, fontSize: 14, color: "#cbd5e1" }}>
            <div>节点总数：{workerSummary.total || 0}</div>
            <div>在线：{workerSummary.online || 0}</div>
            <div>离线：{workerSummary.offline || 0}</div>
            <div>
              最新节点：
              {workerSummary.latest?.display_name || "暂无"}
              {workerSummary.latest?.is_timed_out ? "（心跳超时）" : ""}
            </div>
          </div>
        </Section>
      </section>

      <section
        id="tasks"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(340px, 420px) minmax(0, 1fr)",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <Section title="第 1 步：创建任务" hint="先填标题、来源和链接，别一上来就碰复杂参数。">
          <form onSubmit={createTask} style={{ display: "grid", gap: 12 }}>
            <input
              style={inputStyle}
              value={taskForm.title}
              onChange={(event) => setTaskForm((prev) => ({ ...prev, title: event.target.value }))}
              placeholder="任务标题，例如：YouTube 采集 + 上传 TikTok"
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <input
                style={inputStyle}
                value={taskForm.source_type}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, source_type: event.target.value }))}
                placeholder="来源类型，例如 youtube"
              />
              <input
                style={inputStyle}
                value={taskForm.priority}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, priority: event.target.value }))}
                placeholder="优先级，例如 high"
              />
            </div>
            <input
              style={inputStyle}
              value={taskForm.source_value}
              onChange={(event) => setTaskForm((prev) => ({ ...prev, source_value: event.target.value }))}
              placeholder="来源地址，例如 YouTube 链接"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 120, resize: "vertical" }}
              value={taskForm.payload}
              onChange={(event) => setTaskForm((prev) => ({ ...prev, payload: event.target.value }))}
              placeholder="高级参数 JSON，可先不动"
            />
            <button style={buttonStyle} disabled={busy === "task"}>
              {busy === "task" ? "创建中..." : "创建任务"}
            </button>
          </form>
        </Section>

        <Section
          title="第 2 步：看任务队列"
          hint="这里只保留最关键的几列：状态、分配给谁、能不能重试。"
          action={
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                style={{ ...inputStyle, width: 160 }}
                value={taskFilter}
                onChange={(event) => setTaskFilter(event.target.value)}
                placeholder="按状态过滤"
              />
              <button
                type="button"
                style={buttonStyle}
                onClick={() => {
                  loadTasks(taskFilter);
                  loadTaskSummary();
                }}
              >
                刷新任务
              </button>
            </div>
          }
        >
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                  <th style={{ padding: "10px 8px", width: 70 }}>ID</th>
                  <th style={{ padding: "10px 8px" }}>任务</th>
                  <th style={{ padding: "10px 8px", width: 130 }}>状态</th>
                  <th style={{ padding: "10px 8px", width: 160 }}>Worker</th>
                  <th style={{ padding: "10px 8px", width: 150 }}>尝试情况</th>
                  <th style={{ padding: "10px 8px", width: 220 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}>
                      现在还没有任务。
                    </td>
                  </tr>
                ) : (
                  tasks.map((item) => (
                    <tr key={item.id}>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.id}</td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        <div>{item.title}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          {item.source_type} / {item.source_value || "-"}
                        </div>
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        <select
                          style={inputStyle}
                          value={taskDrafts[item.id]?.status ?? item.status}
                          onChange={(event) => updateTaskDraft(item.id, "status", event.target.value)}
                        >
                          {taskStatusOptions.map((status) => (
                            <option key={status} value={status}>
                              {status}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        <select
                          style={inputStyle}
                          value={taskDrafts[item.id]?.assigned_worker_code ?? item.assigned_worker_code ?? ""}
                          onChange={(event) =>
                            updateTaskDraft(item.id, "assigned_worker_code", event.target.value)
                          }
                        >
                          <option value="">未分配</option>
                          {workers.map((worker) => (
                            <option key={worker.worker_code} value={worker.worker_code}>
                              {worker.display_name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        <div>尝试 {item.attempt_count || 0}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          重试 {item.retry_count || 0}/{item.max_retries || 0}
                        </div>
                        {item.last_error ? (
                          <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>{item.last_error}</div>
                        ) : null}
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <button
                            type="button"
                            style={buttonStyle}
                            onClick={() => saveTaskUpdate(item)}
                            disabled={busy === `task-${item.id}`}
                          >
                            {busy === `task-${item.id}` ? "保存中..." : "保存"}
                          </button>
                          {["failed", "cancelled", "success"].includes(item.status) ? (
                            <button
                              type="button"
                              style={secondaryButtonStyle}
                              onClick={() => retryTask(item.id)}
                              disabled={busy === `retry-${item.id}`}
                            >
                              {busy === `retry-${item.id}` ? "重试中..." : "手动重试"}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>
      </section>

      <section
        id="workers"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(340px, 420px) minmax(0, 1fr)",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <Section title="第 3 步：登记 Worker" hint="先把节点登记上来，后面真实 Worker.exe 跑起来会自动更新这里。">
          <form onSubmit={submitHeartbeat} style={{ display: "grid", gap: 12 }}>
            <input
              style={inputStyle}
              value={workerForm.worker_code}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, worker_code: event.target.value }))}
              placeholder="Worker 编号"
            />
            <input
              style={inputStyle}
              value={workerForm.display_name}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, display_name: event.target.value }))}
              placeholder="显示名称"
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <input
                style={inputStyle}
                value={workerForm.status}
                onChange={(event) => setWorkerForm((prev) => ({ ...prev, status: event.target.value }))}
                placeholder="状态"
              />
              <input
                style={inputStyle}
                value={workerForm.current_task_title}
                onChange={(event) =>
                  setWorkerForm((prev) => ({ ...prev, current_task_title: event.target.value }))
                }
                placeholder="当前任务，可留空"
              />
            </div>
            <input
              style={inputStyle}
              value={workerForm.machine_info}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, machine_info: event.target.value }))}
              placeholder="机器信息"
            />
            <input
              style={inputStyle}
              value={workerForm.capabilities}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, capabilities: event.target.value }))}
              placeholder="能力，逗号分隔"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 100, resize: "vertical" }}
              value={workerForm.heartbeat_note}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, heartbeat_note: event.target.value }))}
              placeholder="备注"
            />
            <button style={buttonStyle} disabled={busy === "worker"}>
              {busy === "worker" ? "提交中..." : "提交 Worker 心跳"}
            </button>
          </form>
        </Section>

        <Section
          title="第 4 步：看 Worker 是否在线"
          hint="只看你最关心的 5 列，不再把技术细节堆满一屏。"
          action={
            <button
              type="button"
              style={buttonStyle}
              onClick={() => {
                loadWorkers();
                loadWorkerSummary();
              }}
            >
              刷新节点
            </button>
          }
        >
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                  <th style={{ padding: "10px 8px" }}>节点</th>
                  <th style={{ padding: "10px 8px", width: 120 }}>当前状态</th>
                  <th style={{ padding: "10px 8px" }}>当前任务</th>
                  <th style={{ padding: "10px 8px" }}>备注</th>
                  <th style={{ padding: "10px 8px", width: 170 }}>最近心跳</th>
                </tr>
              </thead>
              <tbody>
                {workers.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}>
                      现在还没有 Worker 节点。
                    </td>
                  </tr>
                ) : (
                  workers.map((item) => (
                    <tr key={item.id}>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        <div>{item.display_name}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{item.worker_code}</div>
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        {item.status}
                        {item.is_timed_out ? (
                          <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>心跳超时</div>
                        ) : null}
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        {item.current_task_title || "-"}
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        {item.heartbeat_note || "-"}
                      </td>
                      <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                        {formatDate(item.last_heartbeat_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>
      </section>

      <section id="storage" style={{ display: "grid", gap: 16, marginBottom: 16 }}>
        <details style={cardStyle} open>
          <summary style={{ cursor: "pointer", fontSize: 16, fontWeight: 600 }}>
            文件与存储
          </summary>
          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
            <form onSubmit={uploadText} style={{ display: "grid", gap: 12 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>上传一段文本到 R2</div>
              <input
                style={inputStyle}
                value={textPrefix}
                onChange={(event) => setTextPrefix(event.target.value)}
                placeholder="prefix，例如 assets"
              />
              <input
                style={inputStyle}
                value={textFilename}
                onChange={(event) => setTextFilename(event.target.value)}
                placeholder="文件名，可留空"
              />
              <textarea
                style={{ ...inputStyle, minHeight: 120, resize: "vertical" }}
                value={textBody}
                onChange={(event) => setTextBody(event.target.value)}
              />
              <button style={buttonStyle} disabled={busy === "text"}>
                {busy === "text" ? "上传中..." : "上传文本"}
              </button>
            </form>

            <form onSubmit={uploadFile} style={{ display: "grid", gap: 12 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>上传一个本地文件到 R2</div>
              <input
                style={inputStyle}
                value={filePrefix}
                onChange={(event) => setFilePrefix(event.target.value)}
                placeholder="prefix，例如 assets"
              />
              <input
                type="file"
                style={inputStyle}
                onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
              />
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                {selectedFile ? `已选择：${selectedFile.name}` : "请选择一个文件"}
              </div>
              <button style={buttonStyle} disabled={busy === "file"}>
                {busy === "file" ? "上传中..." : "上传文件"}
              </button>
            </form>
          </div>
        </details>

        <details style={cardStyle}>
          <summary style={{ cursor: "pointer", fontSize: 16, fontWeight: 600 }}>
            文件结果与数据库记录
          </summary>
          <div style={{ marginTop: 14, display: "grid", gap: 16 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                style={{ ...inputStyle, width: 220 }}
                value={listPrefix}
                onChange={(event) => setListPrefix(event.target.value)}
                placeholder="prefix"
              />
              <button
                type="button"
                style={buttonStyle}
                onClick={() => {
                  loadAssets(listPrefix);
                  loadRecords(listPrefix);
                }}
              >
                刷新结果
              </button>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                    <th style={{ padding: "10px 8px" }}>R2 文件</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>大小</th>
                    <th style={{ padding: "10px 8px", width: 180 }}>时间</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}>
                        当前前缀下还没有文件。
                      </td>
                    </tr>
                  ) : (
                    assets.map((item) => (
                      <tr key={item.key}>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f", wordBreak: "break-all" }}>
                          {item.key}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.size}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{formatDate(item.last_modified)}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          <button
                            type="button"
                            style={buttonStyle}
                            onClick={() => createPreviewLink(item.key)}
                            disabled={busy === `preview-${item.key}`}
                          >
                            预览
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                    <th style={{ padding: "10px 8px", width: 70 }}>ID</th>
                    <th style={{ padding: "10px 8px", width: 100 }}>来源</th>
                    <th style={{ padding: "10px 8px" }}>Key</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>大小</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}>
                        当前还没有数据库记录。
                      </td>
                    </tr>
                  ) : (
                    records.map((item) => (
                      <tr key={item.id}>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.id}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.source_type}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f", wordBreak: "break-all" }}>{item.key}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.size_bytes}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.status}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      </section>

      <Section title="当前消息" hint="最后一次操作结果，会在这里显示。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>
    </main>
  );
}
