"use client";

import { useEffect, useMemo, useState } from "react";

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

function StatusBadge({ ok, text }) {
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

function SectionHeader({ id, title, hint, action }) {
  return (
    <div
      id={id}
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
  );
}

export default function HomePage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "未配置";

  const [health, setHealth] = useState({ loading: true, ok: false, detail: "" });
  const [summary, setSummary] = useState({
    loading: true,
    total_asset_records: 0,
    total_tasks: 0,
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
  const [listPrefix, setListPrefix] = useState("assets");
  const [taskFilter, setTaskFilter] = useState("");
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

  const latestAsset = useMemo(() => assets[0], [assets]);

  const statCards = [
    {
      title: "API",
      value: health.loading ? "检查中" : health.ok ? "正常" : "异常",
      hint: "Railway FastAPI 服务",
      ok: health.ok,
    },
    {
      title: "数据库",
      value: summary.database_configured ? "已接入" : "未接入",
      hint: "任务 / 资产 / Worker",
      ok: summary.database_configured,
    },
    {
      title: "R2",
      value: summary.storage_configured ? "已接入" : "未接入",
      hint: summary.bucket || "对象存储",
      ok: summary.storage_configured,
    },
    {
      title: "待处理任务",
      value: String(summary.pending_tasks || 0),
      hint: "pending / queued",
      ok: (summary.pending_tasks || 0) > 0,
    },
    {
      title: "在线 Worker",
      value: String(summary.online_workers || 0),
      hint: "idle / running / online",
      ok: (summary.online_workers || 0) > 0,
    },
    {
      title: "资产记录",
      value: String(summary.total_asset_records || 0),
      hint: "asset_records",
      ok: (summary.total_asset_records || 0) > 0,
    },
  ];

  async function loadHealth() {
    setHealth({ loading: true, ok: false, detail: "" });
    try {
      const data = await readJson(await fetch("/api/health", { cache: "no-store" }));
      setHealth({ loading: false, ok: !!data.ok, detail: JSON.stringify(data) });
    } catch (error) {
      setHealth({ loading: false, ok: false, detail: error.message || "请求失败" });
    }
  }

  async function loadSummary() {
    try {
      const data = await readJson(await fetch("/api/dashboard/summary", { cache: "no-store" }));
      setSummary((prev) => ({ ...prev, loading: false, ...data }));
    } catch (error) {
      setSummary((prev) => ({ ...prev, loading: false }));
      setMessage(error.message || "获取系统摘要失败");
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
      setMessage(error.message || "获取上传记录失败");
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

  async function loadTaskSummary() {
    try {
      const data = await readJson(await fetch("/api/tasks/summary", { cache: "no-store" }));
      setTaskSummary(data);
    } catch (error) {
      setMessage(error.message || "获取任务摘要失败");
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

  async function loadWorkerSummary() {
    try {
      const data = await readJson(await fetch("/api/workers/summary", { cache: "no-store" }));
      setWorkerSummary(data);
    } catch (error) {
      setMessage(error.message || "获取 Worker 摘要失败");
    }
  }

  async function reloadAll() {
    await Promise.all([
      loadHealth(),
      loadSummary(),
      loadAssets(listPrefix),
      loadRecords(listPrefix),
      loadTasks(taskFilter),
      loadTaskSummary(),
      loadWorkers(),
      loadWorkerSummary(),
    ]);
  }

  useEffect(() => {
    reloadAll();
  }, []);

  async function uploadText(event) {
    event.preventDefault();
    setBusy("text");
    setMessage("正在上传文本文件...");
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
      const payload = {
        ...taskForm,
        payload: JSON.parse(taskForm.payload || "{}"),
      };
      const data = await readJson(
        await fetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
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
    setMessage(`正在更新任务 #${task.id}...`);
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
        loadWorkers(),
        loadWorkerSummary(),
        loadSummary(),
      ]);
    } catch (error) {
      setMessage(error.message || "更新任务失败");
    } finally {
      setBusy("");
    }
  }

  async function retryTask(taskId) {
    setBusy(`task-retry-${taskId}`);
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
        loadWorkers(),
        loadWorkerSummary(),
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
    setMessage("正在提交 Worker 心跳...");
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
    setBusy(key);
    try {
      const data = await readJson(await fetch(`/api/assets/presign?key=${encodeURIComponent(key)}`));
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (error) {
      setMessage(error.message || "生成预览链接失败");
    } finally {
      setBusy("");
    }
  }

  const navItems = [
    ["system", "系统总览"],
    ["upload", "存储工作台"],
    ["tasks", "任务中心"],
    ["workers", "Worker 节点"],
    ["assets", "R2 对象列表"],
    ["records", "数据库记录"],
  ];

  return (
    <main style={{ maxWidth: 1500, margin: "0 auto", padding: 24 }}>
      <section
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          marginBottom: 20,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 32 }}>Creator Cockpit</h1>
          <p style={{ margin: "8px 0 0", color: "#94a3b8", fontSize: 14 }}>
            运营中台骨架：系统巡检、R2 存储、任务中心、Worker 节点、数据库记录。
          </p>
        </div>
        <div style={{ ...cardStyle, minWidth: 340 }}>
          <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>当前 API 地址</div>
          <div style={{ fontSize: 13, wordBreak: "break-all" }}>{apiBaseUrl}</div>
          <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button style={buttonStyle} onClick={reloadAll}>
              一键刷新
            </button>
            <button
              style={secondaryButtonStyle}
              onClick={() => window.open("/api/dashboard/summary", "_blank", "noopener,noreferrer")}
            >
              打开摘要 JSON
            </button>
          </div>
        </div>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "260px minmax(0, 1fr)",
          gap: 16,
          alignItems: "start",
        }}
      >
        <aside style={{ ...cardStyle, position: "sticky", top: 24 }}>
          <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 14 }}>后台导航</div>
          <div style={{ display: "grid", gap: 10 }}>
            {navItems.map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  background: "#18213f",
                  color: "#e5e7eb",
                  fontSize: 13,
                  border: "1px solid #26314f",
                  textDecoration: "none",
                }}
              >
                {label}
              </a>
            ))}
          </div>
        </aside>

        <div style={{ display: "grid", gap: 16 }}>
          <section id="system">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
                gap: 16,
              }}
            >
              {statCards.map((item) => (
                <div key={item.title} style={cardStyle}>
                  <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 10 }}>{item.title}</div>
                  <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>{item.value}</div>
                  <StatusBadge ok={item.ok} text={item.hint} />
                </div>
              ))}
            </div>
          </section>

          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
              gap: 16,
            }}
          >
            <div style={cardStyle}>
              <SectionHeader
                title="系统状态"
                hint="当前接入的是 Railway 的 api / Postgres / Redis / R2 组合。"
              />
              <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
                <div>健康检查：{health.detail || "等待结果"}</div>
                <div>Bucket：{summary.bucket || "未配置"}</div>
                <div>最新资产：{summary.latest_asset_record?.key || "暂无"}</div>
                <div>最新任务：{summary.latest_task?.title || "暂无"}</div>
                <div>最新 Worker：{summary.latest_worker?.display_name || "暂无"}</div>
              </div>
            </div>

            <div style={cardStyle}>
              <SectionHeader title="任务概览" hint="任务表已经接上数据库，可先用它做任务中心骨架。" />
              <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
                <div>总任务数：{taskSummary.total || 0}</div>
                <div>待处理：{taskSummary.pending || 0}</div>
                <div>运行中：{taskSummary.running || 0}</div>
                <div>成功：{taskSummary.success || 0}</div>
                <div>失败：{taskSummary.failed || 0}</div>
                <div>最新任务：{taskSummary.latest?.title || "暂无"}</div>
              </div>
            </div>

            <div style={cardStyle}>
              <SectionHeader title="Worker 概览" hint="节点页先走心跳模式，后面再接真实 Worker.exe。" />
              <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
                <div>总节点数：{workerSummary.total || 0}</div>
                <div>在线：{workerSummary.online || 0}</div>
                <div>离线：{workerSummary.offline || 0}</div>
                <div>最新节点：{workerSummary.latest?.display_name || "暂无"}</div>
                <div>
                  节点状态：{workerSummary.latest?.status || "-"}
                  {workerSummary.latest?.is_timed_out ? "（心跳超时）" : ""}
                </div>
              </div>
            </div>
          </section>

          <section
            id="upload"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
              gap: 16,
            }}
          >
            <form style={cardStyle} onSubmit={uploadText}>
              <SectionHeader title="文本上传" hint="快速向 R2 写入文案、字幕、JSON 等小文件。" />
              <div style={{ display: "grid", gap: 12 }}>
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
                  placeholder="文件名，可留空自动生成"
                />
                <textarea
                  style={{ ...inputStyle, minHeight: 140, resize: "vertical" }}
                  value={textBody}
                  onChange={(event) => setTextBody(event.target.value)}
                />
                <button style={buttonStyle} disabled={busy === "text"}>
                  {busy === "text" ? "上传中..." : "上传文本到 R2"}
                </button>
              </div>
            </form>

            <form style={cardStyle} onSubmit={uploadFile}>
              <SectionHeader title="文件上传" hint="后面可直接复用给素材、封面、字幕包上传。" />
              <div style={{ display: "grid", gap: 12 }}>
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
                  {selectedFile ? `已选择：${selectedFile.name}` : "请选择一个本地文件上传到 R2"}
                </div>
                <button style={buttonStyle} disabled={busy === "file"}>
                  {busy === "file" ? "上传中..." : "上传文件到 R2"}
                </button>
              </div>
            </form>
          </section>

          <section
            id="tasks"
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(360px, 420px) minmax(0, 1fr)",
              gap: 16,
            }}
          >
            <form style={cardStyle} onSubmit={createTask}>
              <SectionHeader title="任务中心" hint="先从手工建任务开始，后面再接员工工作台和发布编排。" />
              <div style={{ display: "grid", gap: 12 }}>
                <input
                  style={inputStyle}
                  value={taskForm.title}
                  onChange={(event) => setTaskForm((prev) => ({ ...prev, title: event.target.value }))}
                  placeholder="任务标题"
                />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <input
                    style={inputStyle}
                    value={taskForm.task_type}
                    onChange={(event) =>
                      setTaskForm((prev) => ({ ...prev, task_type: event.target.value }))
                    }
                    placeholder="task_type"
                  />
                  <input
                    style={inputStyle}
                    value={taskForm.priority}
                    onChange={(event) =>
                      setTaskForm((prev) => ({ ...prev, priority: event.target.value }))
                    }
                    placeholder="priority"
                  />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <input
                    style={inputStyle}
                    value={taskForm.source_type}
                    onChange={(event) =>
                      setTaskForm((prev) => ({ ...prev, source_type: event.target.value }))
                    }
                    placeholder="source_type"
                  />
                  <input
                    style={inputStyle}
                    value={taskForm.source_value}
                    onChange={(event) =>
                      setTaskForm((prev) => ({ ...prev, source_value: event.target.value }))
                    }
                    placeholder="source_value"
                  />
                </div>
                <textarea
                  style={{ ...inputStyle, minHeight: 130, resize: "vertical" }}
                  value={taskForm.payload}
                  onChange={(event) => setTaskForm((prev) => ({ ...prev, payload: event.target.value }))}
                  placeholder="任务 payload JSON"
                />
                <button style={buttonStyle} disabled={busy === "task"}>
                  {busy === "task" ? "创建中..." : "创建任务"}
                </button>
              </div>
            </form>

            <div style={cardStyle}>
              <SectionHeader
                title="任务列表"
                hint="这里先看数据库任务，后面再接任务详情页和状态机。"
                action={
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      style={{ ...inputStyle, width: 180 }}
                      value={taskFilter}
                      onChange={(event) => setTaskFilter(event.target.value)}
                      placeholder="按状态过滤，如 pending"
                    />
                    <button
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
              />
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                      <th style={{ padding: "10px 8px", width: 60 }}>ID</th>
                      <th style={{ padding: "10px 8px" }}>标题</th>
                      <th style={{ padding: "10px 8px", width: 100 }}>类型</th>
                      <th style={{ padding: "10px 8px", width: 140 }}>状态流转</th>
                      <th style={{ padding: "10px 8px", width: 180 }}>指派 Worker</th>
                      <th style={{ padding: "10px 8px", width: 120 }}>尝试/重试</th>
                      <th style={{ padding: "10px 8px", width: 100 }}>优先级</th>
                      <th style={{ padding: "10px 8px", width: 180 }}>操作</th>
                      <th style={{ padding: "10px 8px", width: 180 }}>创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.length === 0 ? (
                      <tr>
                        <td
                          colSpan={8}
                          style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}
                        >
                          当前没有任务记录。
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
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.task_type}</td>
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
                              <option value="">未指派</option>
                              {workers.map((worker) => (
                                <option key={worker.worker_code} value={worker.worker_code}>
                                  {worker.display_name} ({worker.status})
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
                              <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>
                                {item.last_error}
                              </div>
                            ) : null}
                          </td>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.priority}</td>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              <button
                                style={buttonStyle}
                                onClick={() => saveTaskUpdate(item)}
                                disabled={busy === `task-${item.id}`}
                              >
                                {busy === `task-${item.id}` ? "保存中..." : "保存"}
                              </button>
                              {["failed", "cancelled", "success"].includes(item.status) ? (
                                <button
                                  style={secondaryButtonStyle}
                                  onClick={() => retryTask(item.id)}
                                  disabled={busy === `task-retry-${item.id}`}
                                >
                                  {busy === `task-retry-${item.id}` ? "重试中..." : "手动重试"}
                                </button>
                              ) : null}
                            </div>
                          </td>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                            {formatDate(item.created_at)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section
            id="workers"
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(360px, 420px) minmax(0, 1fr)",
              gap: 16,
            }}
          >
            <form style={cardStyle} onSubmit={submitHeartbeat}>
              <SectionHeader title="Worker 节点页" hint="这一步先模拟 Worker 心跳，后面再接真实 exe。" />
              <div style={{ display: "grid", gap: 12 }}>
                <input
                  style={inputStyle}
                  value={workerForm.worker_code}
                  onChange={(event) =>
                    setWorkerForm((prev) => ({ ...prev, worker_code: event.target.value }))
                  }
                  placeholder="worker_code"
                />
                <input
                  style={inputStyle}
                  value={workerForm.display_name}
                  onChange={(event) =>
                    setWorkerForm((prev) => ({ ...prev, display_name: event.target.value }))
                  }
                  placeholder="display_name"
                />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <input
                    style={inputStyle}
                    value={workerForm.status}
                    onChange={(event) =>
                      setWorkerForm((prev) => ({ ...prev, status: event.target.value }))
                    }
                    placeholder="status"
                  />
                  <input
                    style={inputStyle}
                    value={workerForm.current_task_title}
                    onChange={(event) =>
                      setWorkerForm((prev) => ({ ...prev, current_task_title: event.target.value }))
                    }
                    placeholder="current_task_title"
                  />
                </div>
                <input
                  style={inputStyle}
                  value={workerForm.machine_info}
                  onChange={(event) =>
                    setWorkerForm((prev) => ({ ...prev, machine_info: event.target.value }))
                  }
                  placeholder="machine_info"
                />
                <input
                  style={inputStyle}
                  value={workerForm.capabilities}
                  onChange={(event) =>
                    setWorkerForm((prev) => ({ ...prev, capabilities: event.target.value }))
                  }
                  placeholder="capabilities，逗号分隔"
                />
                <textarea
                  style={{ ...inputStyle, minHeight: 110, resize: "vertical" }}
                  value={workerForm.heartbeat_note}
                  onChange={(event) =>
                    setWorkerForm((prev) => ({ ...prev, heartbeat_note: event.target.value }))
                  }
                  placeholder="heartbeat_note"
                />
                <button style={buttonStyle} disabled={busy === "worker"}>
                  {busy === "worker" ? "提交中..." : "提交 Worker 心跳"}
                </button>
              </div>
            </form>

            <div style={cardStyle}>
              <SectionHeader
                title="Worker 节点列表"
                hint="后面可以在这里继续补心跳超时、占用状态、版本号和升级控制。"
                action={
                  <button style={buttonStyle} onClick={() => {
                    loadWorkers();
                    loadWorkerSummary();
                  }}>
                    刷新节点
                  </button>
                }
              />
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                      <th style={{ padding: "10px 8px", width: 130 }}>Worker</th>
                      <th style={{ padding: "10px 8px", width: 100 }}>状态</th>
                      <th style={{ padding: "10px 8px", width: 120 }}>上报状态</th>
                      <th style={{ padding: "10px 8px" }}>能力</th>
                      <th style={{ padding: "10px 8px" }}>当前任务</th>
                      <th style={{ padding: "10px 8px" }}>心跳备注</th>
                      <th style={{ padding: "10px 8px", width: 180 }}>心跳时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workers.length === 0 ? (
                      <tr>
                        <td
                          colSpan={7}
                          style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}
                        >
                          当前还没有 Worker 节点记录。
                        </td>
                      </tr>
                    ) : (
                      workers.map((item) => (
                        <tr key={item.id}>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                            <div>{item.display_name}</div>
                            <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                              {item.worker_code}
                            </div>
                          </td>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                            {item.status}
                            {item.is_timed_out ? (
                              <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>心跳超时</div>
                            ) : null}
                          </td>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.reported_status}</td>
                          <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                            {(item.capabilities || []).join(", ") || "-"}
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
            </div>
          </section>

          <section id="assets" style={cardStyle}>
            <SectionHeader
              title="R2 对象列表"
              hint="查看指定前缀下的对象，并生成预览下载链接。"
              action={
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input
                    style={{ ...inputStyle, width: 220 }}
                    value={listPrefix}
                    onChange={(event) => setListPrefix(event.target.value)}
                    placeholder="prefix"
                  />
                  <button
                    style={buttonStyle}
                    onClick={() => {
                      loadAssets(listPrefix);
                      loadRecords(listPrefix);
                    }}
                  >
                    刷新列表
                  </button>
                </div>
              }
            />
            <div style={{ marginTop: 16, overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                    <th style={{ padding: "10px 8px" }}>Key</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>大小</th>
                    <th style={{ padding: "10px 8px", width: 220 }}>更新时间</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.length === 0 ? (
                    <tr>
                      <td
                        colSpan={4}
                        style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}
                      >
                        当前前缀下暂无对象。
                      </td>
                    </tr>
                  ) : (
                    assets.map((item) => (
                      <tr key={item.key}>
                        <td
                          style={{
                            padding: "12px 8px",
                            borderTop: "1px solid #26314f",
                            wordBreak: "break-all",
                          }}
                        >
                          {item.key}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.size}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {formatDate(item.last_modified)}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          <button
                            style={buttonStyle}
                            onClick={() => createPreviewLink(item.key)}
                            disabled={busy === item.key}
                          >
                            {busy === item.key ? "生成中..." : "预览"}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section id="records" style={cardStyle}>
            <SectionHeader
              title="数据库上传记录"
              hint="这里显示 Postgres 里的 asset_records，可继续扩成审计日志或发布记录。"
            />
            <div style={{ marginBottom: 12, fontSize: 12, color: "#94a3b8" }}>
              当前前缀：{listPrefix} | 最近对象：{latestAsset?.key || "暂无"}
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
                    <th style={{ padding: "10px 8px", width: 220 }}>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        style={{ padding: "14px 8px", color: "#94a3b8", borderTop: "1px solid #26314f" }}
                      >
                        当前前缀下暂无数据库记录。
                      </td>
                    </tr>
                  ) : (
                    records.map((item) => (
                      <tr key={item.id}>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.id}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.source_type}</td>
                        <td
                          style={{
                            padding: "12px 8px",
                            borderTop: "1px solid #26314f",
                            wordBreak: "break-all",
                          }}
                        >
                          {item.key}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {item.size_bytes}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>{item.status}</td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {formatDate(item.created_at)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section style={cardStyle}>
            <SectionHeader title="当前消息" hint="这里会显示最近一次动作、接口报错或刷新结果。" />
            <div style={{ fontSize: 13, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
          </section>
        </div>
      </section>
    </main>
  );
}
