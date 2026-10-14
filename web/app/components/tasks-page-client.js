"use client";

import { useEffect, useState } from "react";
import {
  DashboardShell,
  Section,
  SummaryCard,
  buttonStyle,
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
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [taskForm, setTaskForm] = useState({
    title: "YouTube 采集 + 上传 TikTok",
    task_type: "publish",
    source_type: "youtube",
    source_value: "https://www.youtube.com/watch?v=demo",
    priority: "high",
    payload:
      '{\n' +
      '  "schema_version": "creator-task/v1",\n' +
      '  "source": {\n' +
      '    "asset_key": "",\n' +
      '    "start_seconds": 0,\n' +
      '    "end_seconds": 0\n' +
      '  },\n' +
      '  "publish": {\n' +
      '    "platforms": ["tiktok"],\n' +
      '    "need_subtitles": true\n' +
      '  },\n' +
      '  "output": {\n' +
      '    "prefix": "processed",\n' +
      '    "target_height": 720,\n' +
      '    "video_codec": "libx264",\n' +
      '    "audio_codec": "aac"\n' +
      '  },\n' +
      '  "execution": {\n' +
      '    "max_retries": 2,\n' +
      '    "simulate_fail": false\n' +
      '  },\n' +
      '  "dedupe": {\n' +
      '    "enabled": true,\n' +
      '    "profile": "balanced",\n' +
      '    "intensity": 0.55,\n' +
      '    "seed": 0,\n' +
      '    "randomize": true,\n' +
      '    "trim": {\n' +
      '      "head_seconds": 0.18,\n' +
      '      "tail_seconds": 0.12\n' +
      '    },\n' +
      '    "speed": {\n' +
      '      "min_factor": 1.01,\n' +
      '      "max_factor": 1.035\n' +
      '    },\n' +
      '    "crop": {\n' +
      '      "min_ratio": 0.978,\n' +
      '      "max_ratio": 0.994\n' +
      '    },\n' +
      '    "rotation": {\n' +
      '      "min_degrees": -0.45,\n' +
      '      "max_degrees": 0.45\n' +
      '    },\n' +
      '    "mirror_chance": 0.15,\n' +
      '    "color": {\n' +
      '      "brightness_min": 0.97,\n' +
      '      "brightness_max": 1.04,\n' +
      '      "contrast_min": -4,\n' +
      '      "contrast_max": 8\n' +
      '    }\n' +
      '  }\n' +
      '}',
  });

  async function loadTaskSummary() {
    try {
      const data = await readJson(await fetch("/api/tasks/summary", { cache: "no-store" }));
      setTaskSummary(data);
    } catch (error) {
      setMessage(error.message || "获取任务摘要失败");
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

  async function reloadAll(status = taskFilter) {
    setMessage("正在刷新任务中心...");
    await Promise.all([loadTaskSummary(), loadTasks(status), loadWorkers()]);
    setMessage("任务中心已刷新");
  }

  useEffect(() => {
    reloadAll("");
  }, []);

  function updateTaskDraft(taskId, field, value) {
    setTaskDrafts((prev) => ({
      ...prev,
      [taskId]: {
        ...(prev[taskId] || {}),
        [field]: value,
      },
    }));
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
      await reloadAll(taskFilter);
    } catch (error) {
      setMessage(error.message || "创建任务失败");
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
      await reloadAll(taskFilter);
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
      await reloadAll(taskFilter);
    } catch (error) {
      setMessage(error.message || "任务重试失败");
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
      description="这里专门处理任务创建、状态流转、Worker 分配和失败重试。"
      action={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            style={{ ...inputStyle, width: 160 }}
            value={taskFilter}
            onChange={(event) => setTaskFilter(event.target.value)}
            placeholder="按状态过滤"
          />
          <button type="button" style={buttonStyle} onClick={() => reloadAll(taskFilter)}>
            刷新任务
          </button>
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

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(340px, 420px) minmax(0, 1fr)",
          gap: 16,
        }}
      >
        <Section title="创建任务" hint="先把任务排进去，再交给 Worker 领取执行。">
          <form onSubmit={createTask} style={{ display: "grid", gap: 12 }}>
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
            <button style={buttonStyle} disabled={busy === "task"}>
              {busy === "task" ? "创建中..." : "创建任务"}
            </button>
          </form>
        </Section>

        <Section title="任务队列" hint="这里保留运营最常用的列：状态、分配、尝试次数、重试。">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                  <th style={tableHeadStyle}>任务</th>
                  <th style={{ ...tableHeadStyle, width: 130 }}>状态</th>
                  <th style={{ ...tableHeadStyle, width: 160 }}>Worker</th>
                  <th style={{ ...tableHeadStyle, width: 150 }}>尝试情况</th>
                  <th style={{ ...tableHeadStyle, width: 220 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      当前筛选条件下还没有任务。
                    </td>
                  </tr>
                ) : (
                  tasks.map((item) => (
                    <tr key={item.id}>
                      <td style={tableCellStyle}>{item.id}</td>
                      <td style={tableCellStyle}>
                        <div>{item.title}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          {item.source_type} / {item.source_value || "-"}
                        </div>
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

      <Section title="当前消息" hint="最近一次创建、更新或重试结果。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>
    </DashboardShell>
  );
}
