"use client";

import { useEffect, useState } from "react";
import {
  DashboardShell,
  Section,
  SummaryCard,
  buttonStyle,
  cardStyle,
  inputStyle,
  readJson,
  secondaryButtonStyle,
  taskStatusOptions,
} from "./dashboard-ui";

const tableHeadStyle = {
  padding: "10px 8px",
  textAlign: "left",
  color: "#94a3b8",
};

const tableCellStyle = {
  padding: "12px 8px",
  borderTop: "1px solid #26314f",
  verticalAlign: "top",
};

const outputPathStyle = {
  padding: "6px 10px",
  borderRadius: 8,
  border: "1px solid #26314f",
  background: "#0f172a",
  color: "#cbd5e1",
  fontSize: 12,
  lineHeight: 1.45,
  minHeight: 40,
  boxSizing: "border-box",
};

const compactInfoLabelStyle = {
  color: "#94a3b8",
  flex: "0 0 auto",
};

const compactInfoValueStyle = {
  minWidth: 0,
  flex: "1 1 auto",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const compactInfoButtonStyle = {
  ...secondaryButtonStyle,
  padding: "0 10px",
  fontSize: 12,
  height: 28,
  minWidth: 84,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  whiteSpace: "nowrap",
};

const taskActionButtonStyle = {
  ...buttonStyle,
  height: 38,
  minWidth: 56,
  padding: "0 16px",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  whiteSpace: "nowrap",
};

const taskSecondaryActionButtonStyle = {
  ...secondaryButtonStyle,
  height: 38,
  minWidth: 84,
  padding: "0 16px",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  whiteSpace: "nowrap",
};

function CopyableInfoRow({ label, value, copyValue, onClick, title }) {
  if (!value) {
    return null;
  }

  const handleClick = onClick ?? (() => {});

  return (
    <button
      type="button"
      onClick={handleClick}
      title={title || value}
      style={{
        ...outputPathStyle,
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 8,
        textAlign: "left",
        cursor: "pointer",
      }}
      data-copy-value={copyValue || value}
    >
      <span style={compactInfoLabelStyle}>{label}</span>
      <span style={compactInfoValueStyle}>{value}</span>
    </button>
  );
};

function buildTaskPayload(profile = "balanced") {
  const profileConfigs = {
    balanced: {
      intensity: 0.55,
      trim: { head_seconds: 0.18, tail_seconds: 0.12 },
      speed: { min_factor: 1.01, max_factor: 1.035 },
      crop: { min_ratio: 0.978, max_ratio: 0.994 },
      rotation: { min_degrees: -0.45, max_degrees: 0.45 },
      mirror_chance: 0.15,
      color: { brightness_min: 0.97, brightness_max: 1.04, contrast_min: -4, contrast_max: 8 },
    },
    aggressive: {
      intensity: 0.8,
      trim: { head_seconds: 0.35, tail_seconds: 0.22 },
      speed: { min_factor: 1.015, max_factor: 1.06 },
      crop: { min_ratio: 0.965, max_ratio: 0.99 },
      rotation: { min_degrees: -0.9, max_degrees: 0.9 },
      mirror_chance: 0.28,
      color: { brightness_min: 0.95, brightness_max: 1.06, contrast_min: -6, contrast_max: 12 },
    },
  };

  return {
    schema_version: "creator-task/v1",
    source: {
      asset_key: "",
      start_seconds: 0,
      end_seconds: 0,
    },
    publish: {
      platforms: ["tiktok"],
      need_subtitles: true,
    },
    output: {
      prefix: "processed",
      target_height: 720,
      video_codec: "libx264",
      audio_codec: "aac",
    },
    execution: {
      max_retries: 2,
      simulate_fail: false,
    },
    dedupe: {
      enabled: true,
      profile,
      seed: 0,
      randomize: true,
      ...profileConfigs[profile],
    },
  };
}

function buildTaskFormPreset({ title, sourceValue, profile = "balanced" }) {
  return {
    title,
    task_type: "publish",
    source_type: "youtube",
    source_value: sourceValue,
    priority: "high",
    payload: JSON.stringify(buildTaskPayload(profile), null, 2),
  };
}

const quickTaskPresets = [
  {
    key: "youtube_real_balanced",
    label: "真实任务模板",
    hint: "复用刚跑通的 YouTube Shorts 去重模板，适合直接批量下发。",
    form: buildTaskFormPreset({
      title: "真实任务-YouTubeShorts-批量去重发布",
      sourceValue: "https://www.youtube.com/shorts/QfZnSS1hgy0",
      profile: "balanced",
    }),
  },
  {
    key: "youtube_real_aggressive",
    label: "加强去重模板",
    hint: "更激进的裁剪、变速和色彩扰动，适合二次压重。",
    form: buildTaskFormPreset({
      title: "真实任务-YouTubeShorts-加强去重发布",
      sourceValue: "https://www.youtube.com/shorts/QfZnSS1hgy0",
      profile: "aggressive",
    }),
  },
];

function getTaskOutputInfo(task) {
  const output = task?.result?.output || {};
  const source = output.source || {};
  const asset = output.asset || {};

  return {
    localFinalPath: source.final_path || "",
    r2Url: asset.storage_url || "",
    r2Key: asset.key || "",
  };
}

function ResultLink({ href, label }) {
  if (!href) {
    return null;
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      style={{
        color: "#818cf8",
        textDecoration: "none",
        fontSize: 12,
      }}
    >
      {label}
    </a>
  );
}

function PresignedLinkRow({ label, href, onGenerate, generating, copyValue, onCopy }) {
  return (
    <div
      style={{
        ...outputPathStyle,
        display: "grid",
        gridTemplateColumns: "72px minmax(0, 1fr) auto",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span style={compactInfoLabelStyle}>{label}</span>
      <span
        style={{
          ...compactInfoValueStyle,
          color: href ? "#cbd5e1" : "#64748b",
        }}
        title={href || copyValue || "点击生成下载链接"}
      >
        {href ? "已生成预签名下载链接" : copyValue || "点击生成下载链接"}
      </span>
      {href ? (
        <div style={{ display: "flex", gap: 6 }}>
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            style={{
              ...compactInfoButtonStyle,
              color: "#818cf8",
              textDecoration: "none",
            }}
          >
            打开
          </a>
          <button type="button" style={compactInfoButtonStyle} onClick={onCopy}>
            复制
          </button>
        </div>
      ) : (
        <button type="button" style={compactInfoButtonStyle} onClick={onGenerate}>
          {generating ? "生成中..." : "生成链接"}
        </button>
      )}
    </div>
  );
}

function getSelectedWorkerCode(task, taskDrafts, workers) {
  const draftedWorkerCode = taskDrafts[task.id]?.assigned_worker_code;
  const currentWorkerCode = draftedWorkerCode ?? task.assigned_worker_code ?? "";

  if (workers.length === 0) {
    return "";
  }

  const matchedWorker = workers.find((worker) => worker.worker_code === currentWorkerCode);
  if (matchedWorker) {
    return matchedWorker.worker_code;
  }

  return workers[0].worker_code;
}

export default function TasksPageClient() {
  const [tasks, setTasks] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [taskSummary, setTaskSummary] = useState({
    total: 0,
    pending: 0,
    running: 0,
    success: 0,
    failed: 0,
  });
  const [taskDrafts, setTaskDrafts] = useState({});
  const [taskFilter, setTaskFilter] = useState("");
  const [pageSize, setPageSize] = useState("20");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [presignedUrls, setPresignedUrls] = useState({});
  const [taskForm, setTaskForm] = useState(() => quickTaskPresets[0].form);
  const [batchSources, setBatchSources] = useState(
    "https://www.youtube.com/shorts/QfZnSS1hgy0"
  );

  async function loadTaskSummary() {
    try {
      const data = await readJson(await fetch("/api/tasks/summary", { cache: "no-store" }));
      setTaskSummary(data);
    } catch (error) {
      setMessage(error.message || "获取任务摘要失败");
    }
  }

  async function loadTasks(status = taskFilter, limit = pageSize) {
    try {
      const data = await readJson(
        await fetch(
          `/api/tasks?status=${encodeURIComponent(status)}&limit=${encodeURIComponent(limit)}`,
          { cache: "no-store" }
        )
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

  async function reloadAll(status = taskFilter, limit = pageSize) {
    setMessage("正在刷新任务中心...");
    await Promise.all([loadTaskSummary(), loadTasks(status, limit), loadWorkers()]);
    setMessage("任务中心已刷新");
  }

  useEffect(() => {
    reloadAll("", "20");
  }, []);

  async function copyText(value, successText) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setMessage(successText || "已复制");
    } catch (error) {
      setMessage(error.message || "复制失败");
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

  function parseTaskPayload() {
    return JSON.parse(taskForm.payload || "{}");
  }

  function buildTaskRequest(sourceValue, index = 0) {
    const suffix = index > 0 ? `-${String(index + 1).padStart(2, "0")}` : "";
    return {
      ...taskForm,
      title: `${taskForm.title}${suffix}`,
      source_value: sourceValue,
      payload: parseTaskPayload(),
    };
  }

  function applyQuickPreset(preset) {
    setTaskForm(preset.form);
    setBatchSources(preset.form.source_value);
    setMessage(`已载入预设：${preset.label}`);
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
          body: JSON.stringify(buildTaskRequest(taskForm.source_value)),
        })
      );
      setMessage(`任务已创建：#${data.item.id} ${data.item.title}`);
      await reloadAll(taskFilter, pageSize);
    } catch (error) {
      setMessage(error.message || "创建任务失败");
    } finally {
      setBusy("");
    }
  }

  async function createBatchTasks() {
    const sources = batchSources
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);

    if (sources.length === 0) {
      setMessage("请先填入至少一条来源地址");
      return;
    }

    setBusy("batch");
    setMessage(`正在批量创建 ${sources.length} 条任务...`);
    try {
      const created = [];
      for (let index = 0; index < sources.length; index += 1) {
        const response = await fetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildTaskRequest(sources[index], index)),
        });
        const data = await readJson(response);
        created.push(`#${data.item.id}`);
      }
      setMessage(`批量任务已创建：${created.join("、")}`);
      await reloadAll(taskFilter, pageSize);
    } catch (error) {
      setMessage(error.message || "批量创建任务失败");
    } finally {
      setBusy("");
    }
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
      setTaskDrafts((prev) => {
        const next = { ...prev };
        delete next[task.id];
        return next;
      });
      setMessage(`任务已更新：#${data.item.id} -> ${data.item.status}`);
      await reloadAll(taskFilter, pageSize);
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
      await reloadAll(taskFilter, pageSize);
    } catch (error) {
      setMessage(error.message || "任务重试失败");
    } finally {
      setBusy("");
    }
  }

  async function openPresignedUrl(taskId, key) {
    if (!key) {
      setMessage("当前任务缺少 R2 key");
      return;
    }

    setBusy(`presign-${taskId}`);
    setMessage(`正在生成任务 #${taskId} 的下载链接...`);
    try {
      const data = await readJson(
        await fetch(`/api/assets/presign?key=${encodeURIComponent(key)}`, {
          cache: "no-store",
        })
      );
      setPresignedUrls((prev) => ({
        ...prev,
        [taskId]: data.url,
      }));
      window.open(data.url, "_blank", "noopener,noreferrer");
      setMessage(`任务 #${taskId} 的预签名链接已生成`);
    } catch (error) {
      setMessage(error.message || "生成预签名链接失败");
    } finally {
      setBusy("");
    }
  }

  const summaryCards = [
    {
      label: "任务总数",
      value: String(taskSummary.total || 0),
      hint: "当前已登记任务",
      ok: true,
    },
    {
      label: "待处理",
      value: String(taskSummary.pending || 0),
      hint: "等待分配或领取",
      ok: (taskSummary.pending || 0) > 0,
    },
    {
      label: "运行中",
      value: String(taskSummary.running || 0),
      hint: "Worker 正在执行",
      ok: (taskSummary.running || 0) > 0,
    },
    {
      label: "失败任务",
      value: String(taskSummary.failed || 0),
      hint: "优先关注是否需要重试",
      ok: (taskSummary.failed || 0) === 0,
    },
  ];

  return (
    <DashboardShell
      title="任务中心"
      description={
        <div>这里专门处理任务创建、状态流转、Worker 分配和失败重试。</div>
      }
      action={
        <div style={{ display: "grid", gap: 10, minWidth: "min(100%, 560px)" }}>
          <div
            style={{
              padding: "8px 12px",
              borderRadius: 10,
              border: "1px solid #26314f",
              background: "#0f172a",
              color: "#cbd5e1",
              fontSize: 13,
              lineHeight: 1.3,
            }}
          >
            当前消息：{message}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <input
              style={{ ...inputStyle, width: 160 }}
              value={taskFilter}
              onChange={(event) => setTaskFilter(event.target.value)}
              placeholder="按状态过滤"
            />
            <select
              style={{ ...inputStyle, width: 110 }}
              value={pageSize}
              onChange={(event) => {
                const nextValue = event.target.value;
                setPageSize(nextValue);
                reloadAll(taskFilter, nextValue);
              }}
            >
              {["20", "50", "100"].map((value) => (
                <option key={value} value={value}>
                  每页 {value}
                </option>
              ))}
            </select>
            <button type="button" style={buttonStyle} onClick={() => reloadAll(taskFilter, pageSize)}>
              刷新任务
            </button>
          </div>
        </div>
      }
    >
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 16,
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

      <div style={{ display: "grid", gap: 16 }}>
        <Section
          title="批量来源"
          hint="每行一条来源地址，点一次就能把同一模板批量排进任务队列。"
          action={
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              当前共 {batchSources.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).length} 条
            </div>
          }
        >
          <div style={{ display: "grid", gap: 12 }}>
            <textarea
              style={{ ...inputStyle, minHeight: 132, resize: "vertical" }}
              value={batchSources}
              onChange={(event) => setBatchSources(event.target.value)}
              placeholder={"每行一条来源地址\nhttps://www.youtube.com/shorts/xxx\nhttps://www.youtube.com/shorts/yyy"}
            />
            <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>
              批量创建时会沿用下方“创建任务”里的 `title / priority / payload`，并自动生成 `-01 / -02 / -03`
              这样的标题后缀。
            </div>
          </div>
        </Section>

        <Section title="创建任务" hint="先把任务排进去，再交给 Worker 领取执行。">
          <form onSubmit={createTask} style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gap: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#cbd5e1" }}>快捷预设</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8 }}>
                {quickTaskPresets.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    style={{
                      ...secondaryButtonStyle,
                      textAlign: "left",
                      display: "grid",
                      gap: 4,
                      padding: "10px 14px",
                    }}
                    onClick={() => applyQuickPreset(preset)}
                  >
                    <span style={{ fontWeight: 600 }}>{preset.label}</span>
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>{preset.hint}</span>
                  </button>
                ))}
              </div>
            </div>
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
                onChange={(event) => setTaskForm((prev) => ({ ...prev, task_type: event.target.value }))}
                placeholder="任务类型"
              />
              <input
                style={inputStyle}
                value={taskForm.priority}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, priority: event.target.value }))}
                placeholder="优先级"
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <input
                style={inputStyle}
                value={taskForm.source_type}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, source_type: event.target.value }))}
                placeholder="来源类型"
              />
              <input
                style={inputStyle}
                value={taskForm.source_value}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, source_value: event.target.value }))}
                placeholder="来源地址"
              />
            </div>
            <textarea
              style={{ ...inputStyle, minHeight: 140, resize: "vertical" }}
              value={taskForm.payload}
              onChange={(event) => setTaskForm((prev) => ({ ...prev, payload: event.target.value }))}
              placeholder="正式任务 payload JSON（creator-task/v1）"
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button style={buttonStyle} disabled={busy === "task" || busy === "batch"}>
                {busy === "task" ? "创建中..." : "创建任务"}
              </button>
              <button
                type="button"
                style={secondaryButtonStyle}
                disabled={busy === "task" || busy === "batch"}
                onClick={createBatchTasks}
              >
                {busy === "batch" ? "批量创建中..." : "按上方来源批量创建"}
              </button>
            </div>
          </form>
        </Section>

        <Section
          title="任务队列"
          hint="这里保留运营最常用的列：状态、分配、尝试次数、重试。"
          action={
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              共 {taskSummary.total || 0} 条，当前每页 {pageSize} 条
            </div>
          }
        >
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                  <th style={tableHeadStyle}>任务</th>
                  <th style={{ ...tableHeadStyle, width: 320 }}>产物</th>
                  <th style={{ ...tableHeadStyle, width: 130 }}>状态</th>
                  <th style={{ ...tableHeadStyle, width: 160 }}>Worker</th>
                  <th style={{ ...tableHeadStyle, width: 150 }}>尝试情况</th>
                  <th style={{ ...tableHeadStyle, width: 220 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      当前筛选条件下还没有任务。
                    </td>
                  </tr>
                ) : (
                  tasks.map((item) => {
                    const outputInfo = getTaskOutputInfo(item);
                    const selectedWorkerCode = getSelectedWorkerCode(item, taskDrafts, workers);
                    return (
                      <tr key={item.id}>
                        <td style={tableCellStyle}>{item.id}</td>
                        <td style={tableCellStyle}>
                          <div>{item.title}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            {item.source_type} / {item.source_value || "-"}
                          </div>
                        </td>
                        <td style={tableCellStyle}>
                          {item.status === "success" && (outputInfo.localFinalPath || outputInfo.r2Url) ? (
                            <div style={{ display: "grid", gap: 6 }}>
                              {outputInfo.localFinalPath ? (
                                <CopyableInfoRow
                                  label="本地文件路径"
                                  value={outputInfo.localFinalPath}
                                  onClick={() =>
                                    copyText(outputInfo.localFinalPath, `已复制本地路径：任务 ${item.id}`)
                                  }
                                />
                              ) : null}
                              {outputInfo.r2Key ? (
                                <PresignedLinkRow
                                  label="R2 下载"
                                  href={presignedUrls[item.id] || ""}
                                  copyValue={outputInfo.r2Key}
                                  generating={busy === `presign-${item.id}`}
                                  onGenerate={() => openPresignedUrl(item.id, outputInfo.r2Key)}
                                  onCopy={() =>
                                    copyText(
                                      presignedUrls[item.id] || outputInfo.r2Key,
                                      `已复制 R2 信息：任务 ${item.id}`
                                    )
                                  }
                                />
                              ) : null}
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color: "#94a3b8" }}>
                              {item.status === "success" ? "本次任务暂无产物信息" : "任务成功后会在这里显示本地路径和 R2 链接"}
                            </div>
                          )}
                        </td>
                        <td style={tableCellStyle}>
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
                        <td style={tableCellStyle}>
                          <select
                            style={inputStyle}
                            value={selectedWorkerCode}
                            onChange={(event) =>
                              updateTaskDraft(item.id, "assigned_worker_code", event.target.value)
                            }
                          >
                            {workers.length === 0 ? (
                              <option value="">未分配</option>
                            ) : (
                              workers.map((worker) => (
                                <option key={worker.worker_code} value={worker.worker_code}>
                                  {worker.display_name}
                                </option>
                              ))
                            )}
                          </select>
                        </td>
                        <td style={tableCellStyle}>
                          <div>尝试 {item.attempt_count || 0}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            重试 {item.retry_count || 0}/{item.max_retries || 0}
                          </div>
                          {item.last_error ? (
                            <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>{item.last_error}</div>
                          ) : null}
                        </td>
                        <td style={tableCellStyle}>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <button
                              type="button"
                              style={taskActionButtonStyle}
                              onClick={() => saveTaskUpdate(item)}
                              disabled={busy === `task-${item.id}`}
                            >
                              {busy === `task-${item.id}` ? "保存中..." : "保存"}
                            </button>
                            {["failed", "cancelled", "success"].includes(item.status) ? (
                              <button
                                type="button"
                                style={taskSecondaryActionButtonStyle}
                                onClick={() => retryTask(item.id)}
                                disabled={busy === `retry-${item.id}`}
                              >
                                {busy === `retry-${item.id}` ? "重试中..." : "手动重试"}
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </DashboardShell>
  );
}
