"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  DashboardShell,
  Section,
  SummaryCard,
  authFetch,
  buttonStyle,
  cardStyle,
  setStoredPublishDraft,
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

function buildAgentFlowPayload(topicSeed = "围绕AI短视频批量起号，生成可连续扩写的内容方向") {
  return {
    schema_version: "creator-task/v1",
    source: {
      asset_key: "",
      start_seconds: 0,
      end_seconds: 0,
    },
    publish: {
      platforms: ["tiktok"],
      need_subtitles: false,
    },
    output: {
      prefix: "agent-flow",
      target_height: 720,
      video_codec: "libx264",
      audio_codec: "aac",
    },
    execution: {
      max_retries: 1,
      simulate_fail: false,
      required_capabilities: ["llm-agent"],
      preferred_worker_codes: [],
      lease_timeout_seconds: 1800,
    },
    agent_flow: {
      goal: "选题/提示词优化/发布文案生成",
      topic_seed: topicSeed,
      platform: "tiktok",
      audience: "想做AI视频副业的新手创作者",
      tone: "高点击、强反差、适合短视频口播",
      language: "zh-CN",
      reference_prompt: "",
      reference_copy: "",
      deepseek: {
        enabled: true,
        model: "deepseek-chat",
        temperature: 0.8,
        max_topics: 5,
      },
      video: {
        enabled: false,
        provider: "agnes",
        model: "agnes-video-2.5-flash",
        seconds: "5",
        size: "1280x720",
        poll_timeout_seconds: 120,
        poll_interval_seconds: 10,
      },
    },
    dedupe: {
      enabled: false,
      profile: "balanced",
      seed: 0,
      randomize: true,
    },
  };
}

function buildAgentFlowFormPreset() {
  const topicSeed = "围绕AI短视频批量起号，生成可连续扩写的内容方向";
  return {
    title: "AI文案工作流-选题提示词文案生成",
    source_value: "账号定位：AI短视频批量起号；目标：先生成可直接投喂视频模型和发布中心的文案骨架",
    priority: "high",
    group_id: "",
    preferred_worker_codes: "",
    lease_timeout_seconds: "1800",
    payload: JSON.stringify(buildAgentFlowPayload(topicSeed), null, 2),
  };
}

function parseCsvInput(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function getDeepseekResult(task) {
  return task?.result?.agent_flow?.deepseek || {};
}

function getVideoResult(task) {
  return task?.result?.agent_flow?.video || {};
}

function buildPublishDraft(task) {
  const deepseek = getDeepseekResult(task);
  const publishCopy = deepseek.publish_copy || {};
  const video = getVideoResult(task);
  const hashtags = Array.isArray(publishCopy.hashtags)
    ? publishCopy.hashtags.join(" ")
    : String(publishCopy.hashtags || "").trim();

  return {
    source: "agent_flow",
    task_id: task.id,
    task_title: task.title || "",
    group_id: task.group_id || null,
    selected_topic: deepseek.selected_topic || "",
    optimized_prompt: deepseek.optimized_prompt || "",
    video_prompt: deepseek.video_prompt || "",
    video_url: video.video_url || "",
    source_value: task.source_value || "",
    publish: {
      title: publishCopy.title || "",
      hook: publishCopy.hook || "",
      caption: publishCopy.caption || "",
      hashtags,
    },
    copied_at: new Date().toISOString(),
  };
}

export default function AgentFlowPageClient() {
  const router = useRouter();
  const [groups, setGroups] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [summary, setSummary] = useState({
    total: 0,
    pending: 0,
    running: 0,
    success: 0,
    failed: 0,
  });
  const [taskDrafts, setTaskDrafts] = useState({});
  const [groupFilter, setGroupFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [pageSize, setPageSize] = useState("20");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [taskForm, setTaskForm] = useState(() => buildAgentFlowFormPreset());
  const [batchTopics, setBatchTopics] = useState(
    "围绕AI短视频批量起号，生成一组适合连续更新的内容方向"
  );

  async function loadGroups() {
    try {
      const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
      setGroups(data.items || []);
    } catch (error) {
      setGroups([]);
      setMessage(error.message || "获取账号组失败");
    }
  }

  async function loadWorkers() {
    try {
      const data = await readJson(await authFetch("/api/workers", { cache: "no-store" }));
      setWorkers((data.items || []).filter((item) => (item.capabilities || []).includes("llm-agent")));
    } catch (error) {
      setWorkers([]);
      setMessage(error.message || "获取 Worker 列表失败");
    }
  }

  async function loadSummary(nextGroupId = groupFilter) {
    try {
      const data = await readJson(
        await authFetch(
          `/api/tasks/summary?task_type=agent_flow&group_id=${encodeURIComponent(nextGroupId)}`,
          { cache: "no-store" }
        )
      );
      setSummary(data);
    } catch (error) {
      setMessage(error.message || "获取 AI 文案任务摘要失败");
    }
  }

  async function loadTasks(nextStatus = statusFilter, nextLimit = pageSize, nextGroupId = groupFilter) {
    try {
      const data = await readJson(
        await authFetch(
          `/api/tasks?task_type=agent_flow&status=${encodeURIComponent(nextStatus)}&group_id=${encodeURIComponent(nextGroupId)}&limit=${encodeURIComponent(nextLimit)}`,
          { cache: "no-store" }
        )
      );
      setTasks(data.items || []);
    } catch (error) {
      setTasks([]);
      setMessage(error.message || "获取 AI 文案任务列表失败");
    }
  }

  async function reloadAll(nextStatus = statusFilter, nextLimit = pageSize, nextGroupId = groupFilter) {
    setMessage("正在刷新 AI 文案工作流...");
    await Promise.all([loadGroups(), loadWorkers(), loadSummary(nextGroupId), loadTasks(nextStatus, nextLimit, nextGroupId)]);
    setMessage("AI 文案工作流已刷新");
  }

  useEffect(() => {
    reloadAll("", "20", "");
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

  function parseTaskPayload() {
    return JSON.parse(taskForm.payload || "{}");
  }

  function buildTaskRequest(sourceValue, topicSeed, index = 0) {
    const suffix = index > 0 ? `-${String(index + 1).padStart(2, "0")}` : "";
    const payload = parseTaskPayload();
    payload.execution = {
      ...(payload.execution || {}),
      required_capabilities: ["llm-agent"],
      preferred_worker_codes: parseCsvInput(taskForm.preferred_worker_codes),
      lease_timeout_seconds: Number(taskForm.lease_timeout_seconds || 1800),
    };
    payload.agent_flow = {
      ...(payload.agent_flow || {}),
      topic_seed: topicSeed,
    };
    return {
      title: `${taskForm.title}${suffix}`,
      task_type: "agent_flow",
      source_type: "manual",
      source_value: sourceValue,
      priority: taskForm.priority,
      group_id: taskForm.group_id ? Number(taskForm.group_id) : null,
      payload,
    };
  }

  async function createTask(event) {
    event.preventDefault();
    setBusy("create");
    setMessage("正在创建 AI 文案任务...");
    try {
      const payload = parseTaskPayload();
      const topicSeed = payload?.agent_flow?.topic_seed || "";
      const data = await readJson(
        await authFetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildTaskRequest(taskForm.source_value, topicSeed)),
        })
      );
      setMessage(`AI 文案任务已创建：#${data.item.id} ${data.item.title}`);
      await reloadAll(statusFilter, pageSize, groupFilter);
    } catch (error) {
      setMessage(error.message || "创建 AI 文案任务失败");
    } finally {
      setBusy("");
    }
  }

  async function createBatchTasks() {
    const seeds = batchTopics
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);

    if (seeds.length === 0) {
      setMessage("请先填入至少一条批量选题方向");
      return;
    }

    setBusy("batch");
    setMessage(`正在批量创建 ${seeds.length} 条 AI 文案任务...`);
    try {
      const created = [];
      for (let index = 0; index < seeds.length; index += 1) {
        const response = await authFetch("/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildTaskRequest(seeds[index], seeds[index], index)),
        });
        const data = await readJson(response);
        created.push(`#${data.item.id}`);
      }
      setMessage(`批量 AI 文案任务已创建：${created.join("、")}`);
      await reloadAll(statusFilter, pageSize, groupFilter);
    } catch (error) {
      setMessage(error.message || "批量创建 AI 文案任务失败");
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
        await authFetch(`/api/tasks/${task.id}`, {
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
      setMessage(`AI 文案任务已更新：#${data.item.id} -> ${data.item.status}`);
      await reloadAll(statusFilter, pageSize, groupFilter);
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
        await authFetch(`/api/tasks/${taskId}/retry`, {
          method: "POST",
        })
      );
      setMessage(`任务已重试入队：#${data.item.id}`);
      await reloadAll(statusFilter, pageSize, groupFilter);
    } catch (error) {
      setMessage(error.message || "任务重试失败");
    } finally {
      setBusy("");
    }
  }

  function sendToPublish(task) {
    try {
      const draft = buildPublishDraft(task);
      setStoredPublishDraft(draft);
      setMessage(`任务 #${task.id} 的结果已送到发布中心草稿`);
      router.push("/publish");
    } catch (error) {
      setMessage(error.message || "推送到发布中心失败");
    }
  }

  const summaryCards = [
    {
      label: "AI 文案任务",
      value: String(summary.total || 0),
      hint: "当前 agent_flow 总量",
      ok: true,
    },
    {
      label: "待处理",
      value: String(summary.pending || 0),
      hint: "等待 LLM Worker 领取",
      ok: (summary.pending || 0) > 0,
    },
    {
      label: "运行中",
      value: String(summary.running || 0),
      hint: "正在生成选题和文案",
      ok: (summary.running || 0) > 0,
    },
    {
      label: "可用 LLM Worker",
      value: String(workers.length || 0),
      hint: "带 llm-agent 能力",
      ok: workers.length > 0,
    },
  ];

  return (
    <DashboardShell
      title="AI文案工作流"
      description="这里单独处理选题、提示词优化、发布文案和可选视频提示词，不和普通任务中心混在一起。"
      action={
        <div style={{ display: "grid", gap: 10, minWidth: "min(100%, 620px)" }}>
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
            <select
              style={{ ...inputStyle, width: 180 }}
              value={groupFilter}
              onChange={(event) => {
                const nextValue = event.target.value;
                setGroupFilter(nextValue);
                reloadAll(statusFilter, pageSize, nextValue);
              }}
            >
              <option value="">全部账号组</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.group_name}
                </option>
              ))}
            </select>
            <input
              style={{ ...inputStyle, width: 150 }}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              placeholder="按状态过滤"
            />
            <select
              style={{ ...inputStyle, width: 110 }}
              value={pageSize}
              onChange={(event) => {
                const nextValue = event.target.value;
                setPageSize(nextValue);
                reloadAll(statusFilter, nextValue, groupFilter);
              }}
            >
              {["20", "50", "100"].map((value) => (
                <option key={value} value={value}>
                  每页 {value}
                </option>
              ))}
            </select>
            <button type="button" style={buttonStyle} onClick={() => reloadAll(statusFilter, pageSize, groupFilter)}>
              刷新页面
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
          <SummaryCard key={item.label} label={item.label} value={item.value} hint={item.hint} ok={item.ok} />
        ))}
      </section>

      <div style={{ display: "grid", gap: 16 }}>
        <Section
          title="批量选题方向"
          hint="每行一条方向，适合一次性生成多条选题和文案骨架。"
          action={
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              当前共 {batchTopics.split(/\r?\n/).map((item) => item.trim()).filter(Boolean).length} 条
            </div>
          }
        >
          <div style={{ display: "grid", gap: 12 }}>
            <textarea
              style={{ ...inputStyle, minHeight: 132, resize: "vertical" }}
              value={batchTopics}
              onChange={(event) => setBatchTopics(event.target.value)}
              placeholder={"每行一条选题方向\nAI短视频批量起号的新手避坑\nAI绘画壁纸号如何做内容裂变"}
            />
            <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>
              批量创建时会把每一行同时写入 `source_value` 和 `agent_flow.topic_seed`，方便直接交给 DeepSeek 产出结果。
            </div>
          </div>
        </Section>

        <Section title="创建 AI 文案任务" hint="表单聚焦 agent_flow，避免普通任务字段干扰。">
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
                value={taskForm.priority}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, priority: event.target.value }))}
                placeholder="优先级"
              />
              <select
                style={inputStyle}
                value={taskForm.group_id}
                onChange={(event) => setTaskForm((prev) => ({ ...prev, group_id: event.target.value }))}
              >
                <option value="">归属账号组（可留空）</option>
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.group_name}
                  </option>
                ))}
              </select>
            </div>
            <textarea
              style={{ ...inputStyle, minHeight: 84, resize: "vertical" }}
              value={taskForm.source_value}
              onChange={(event) => setTaskForm((prev) => ({ ...prev, source_value: event.target.value }))}
              placeholder="业务背景 / 账号定位 / 目标说明"
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <input
                style={inputStyle}
                value={taskForm.preferred_worker_codes}
                onChange={(event) =>
                  setTaskForm((prev) => ({ ...prev, preferred_worker_codes: event.target.value }))
                }
                placeholder="绑定 Worker，可留空"
              />
              <input
                style={inputStyle}
                value={taskForm.lease_timeout_seconds}
                onChange={(event) =>
                  setTaskForm((prev) => ({ ...prev, lease_timeout_seconds: event.target.value }))
                }
                placeholder="租约秒数"
              />
              <input
                style={inputStyle}
                value={workers.map((item) => item.worker_code).join(",")}
                readOnly
                placeholder="可用 LLM Worker"
              />
            </div>
            <textarea
              style={{ ...inputStyle, minHeight: 320, resize: "vertical", fontFamily: "Consolas, monospace" }}
              value={taskForm.payload}
              onChange={(event) => setTaskForm((prev) => ({ ...prev, payload: event.target.value }))}
              placeholder="agent_flow payload JSON"
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="submit" style={buttonStyle} disabled={busy === "create" || busy === "batch"}>
                {busy === "create" ? "创建中..." : "创建 AI 文案任务"}
              </button>
              <button
                type="button"
                style={secondaryButtonStyle}
                disabled={busy === "create" || busy === "batch"}
                onClick={createBatchTasks}
              >
                {busy === "batch" ? "批量创建中..." : "按上方方向批量创建"}
              </button>
              <button
                type="button"
                style={secondaryButtonStyle}
                disabled={busy === "create" || busy === "batch"}
                onClick={() => {
                  const preset = buildAgentFlowFormPreset();
                  setTaskForm(preset);
                  setBatchTopics(JSON.parse(preset.payload).agent_flow.topic_seed || "");
                  setMessage("已恢复默认 AI 文案模板");
                }}
              >
                恢复默认模板
              </button>
            </div>
          </form>
        </Section>

        <Section
          title="AI 文案任务队列"
          hint="这里专门看选题结果、优化提示词、发布文案和可选视频任务状态。"
          action={
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              共 {summary.total || 0} 条，当前每页 {pageSize} 条
            </div>
          }
        >
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                  <th style={tableHeadStyle}>任务</th>
                  <th style={{ ...tableHeadStyle, width: 320 }}>生成结果</th>
                  <th style={{ ...tableHeadStyle, width: 130 }}>状态</th>
                  <th style={{ ...tableHeadStyle, width: 160 }}>Worker</th>
                  <th style={{ ...tableHeadStyle, width: 160 }}>尝试情况</th>
                  <th style={{ ...tableHeadStyle, width: 220 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      当前筛选条件下还没有 AI 文案任务。
                    </td>
                  </tr>
                ) : (
                  tasks.map((item) => {
                    const deepseek = getDeepseekResult(item);
                    const publishCopy = deepseek.publish_copy || {};
                    const video = getVideoResult(item);
                    return (
                      <tr key={item.id}>
                        <td style={tableCellStyle}>{item.id}</td>
                        <td style={tableCellStyle}>
                          <div>{item.title}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            {item.payload?.agent_flow?.topic_seed || item.source_value || "-"}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            组 {item.group_id || "-"} / 创建人 {item.created_by_user_id || "-"} / 最近触发 {item.triggered_by_user_id || "-"}
                          </div>
                        </td>
                        <td style={tableCellStyle}>
                          {item.status === "success" ? (
                            <div style={{ display: "grid", gap: 6 }}>
                              <div style={{ color: "#e2e8f0" }}>选题：{deepseek.selected_topic || "-"}</div>
                              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                                标题：{publishCopy.title || "-"}
                              </div>
                              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                                Hook：{publishCopy.hook || "-"}
                              </div>
                              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                                视频：{video.video_url ? <a href={video.video_url} target="_blank" rel="noreferrer" style={{ color: "#818cf8", textDecoration: "none" }}>查看结果</a> : video.status || "未启用"}
                              </div>
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color: "#94a3b8" }}>
                              任务成功后会在这里显示选题、发布文案和可选视频结果。
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
                            value={taskDrafts[item.id]?.assigned_worker_code ?? item.assigned_worker_code ?? ""}
                            onChange={(event) =>
                              updateTaskDraft(item.id, "assigned_worker_code", event.target.value)
                            }
                          >
                            <option value="">自动分配</option>
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
                            {item.status === "success" ? (
                              <button
                                type="button"
                                style={secondaryButtonStyle}
                                onClick={() => sendToPublish(item)}
                              >
                                推送到发布中心
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
