"use client";

import { useEffect, useMemo, useState } from "react";
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
  formatDate,
} from "./dashboard-ui";

const tableHeadStyle = {
  padding: "10px 8px",
  textAlign: "left",
  color: "#94a3b8",
  fontSize: 12,
  fontWeight: 600,
};

const tableCellStyle = {
  padding: "10px 8px",
  borderTop: "1px solid #26314f",
  verticalAlign: "top",
  fontSize: 13,
};

function buildBriefDraft(template) {
  const currentVersion = template?.current_version || {};
  const modelConfig = currentVersion.default_model_config || {};
  const platforms = Array.isArray(template?.platform_scope) && template.platform_scope.length > 0
    ? template.platform_scope
    : ["tiktok"];
  return {
    goal: "选题/提示词优化/发布文案生成",
    topic_seed: "围绕 AI 短视频批量起号，生成可连续扩写的内容方向",
    platform: platforms[0] || "tiktok",
    audience: "想做 AI 视频副业的新手创作者",
    tone: template?.style_type || "高点击、强反差、适合短视频口播",
    language: "zh-CN",
    reference_prompt: "",
    reference_copy: "",
    max_topics: String(modelConfig?.deepseek?.max_topics || 5),
    video_enabled: Boolean(modelConfig?.video?.enabled),
  };
}

function normalizeBriefPayload(form) {
  return {
    goal: String(form.goal || "").trim(),
    topic_seed: String(form.topic_seed || "").trim(),
    platform: String(form.platform || "tiktok").trim() || "tiktok",
    audience: String(form.audience || "").trim(),
    tone: String(form.tone || "").trim(),
    language: String(form.language || "zh-CN").trim() || "zh-CN",
    reference_prompt: String(form.reference_prompt || "").trim(),
    reference_copy: String(form.reference_copy || "").trim(),
    max_topics: Number(form.max_topics || 5),
    video_enabled: Boolean(form.video_enabled),
  };
}

function renderAssetPreview(asset) {
  if (!asset) {
    return "-";
  }
  if (asset.content_text) {
    return asset.content_text;
  }
  return JSON.stringify(asset.content_json || {}, null, 2);
}

function StatusTag({ status }) {
  const palette = {
    success: { bg: "rgba(34,197,94,.14)", border: "rgba(34,197,94,.35)", color: "#86efac" },
    running: { bg: "rgba(59,130,246,.14)", border: "rgba(59,130,246,.35)", color: "#93c5fd" },
    queued: { bg: "rgba(245,158,11,.14)", border: "rgba(245,158,11,.35)", color: "#fcd34d" },
    pending: { bg: "rgba(148,163,184,.14)", border: "rgba(148,163,184,.35)", color: "#cbd5e1" },
    failed: { bg: "rgba(239,68,68,.14)", border: "rgba(239,68,68,.35)", color: "#fca5a5" },
    cancelled: { bg: "rgba(100,116,139,.14)", border: "rgba(100,116,139,.35)", color: "#cbd5e1" },
  };
  const current = palette[status] || palette.pending;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        borderRadius: 999,
        padding: "4px 10px",
        border: `1px solid ${current.border}`,
        background: current.bg,
        color: current.color,
        fontSize: 12,
        lineHeight: 1,
      }}
    >
      {status || "-"}
    </span>
  );
}

export default function AgentFlowPageClient() {
  const router = useRouter();
  const [groups, setGroups] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [projects, setProjects] = useState([]);
  const [runs, setRuns] = useState([]);
  const [summary, setSummary] = useState({
    total: 0,
    pending: 0,
    running: 0,
    success: 0,
    failed: 0,
  });
  const [stages, setStages] = useState([]);
  const [assets, setAssets] = useState([]);
  const [assetBundle, setAssetBundle] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [pageSize, setPageSize] = useState("20");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [form, setForm] = useState({
    title: "",
    group_id: "",
    project_id: "",
    priority: "100",
    ...buildBriefDraft(null),
  });

  const selectedTemplate = useMemo(
    () => templates.find((item) => String(item.id) === String(selectedTemplateId)) || null,
    [templates, selectedTemplateId]
  );
  const selectedRun = useMemo(
    () => runs.find((item) => String(item.id) === String(selectedRunId)) || null,
    [runs, selectedRunId]
  );

  async function loadGroups() {
    const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
    setGroups(data.items || []);
  }

  async function loadWorkers() {
    const data = await readJson(await authFetch("/api/workers", { cache: "no-store" }));
    setWorkers((data.items || []).filter((item) => (item.capabilities || []).includes("llm-agent")));
  }

  async function loadTemplates(nextGroupId = groupFilter) {
    const data = await readJson(
      await authFetch(
        `/api/agent-flow/templates?group_id=${encodeURIComponent(nextGroupId)}`,
        { cache: "no-store" }
      )
    );
    const items = data.items || [];
    setTemplates(items);
    if (!selectedTemplateId && items.length > 0) {
      const template = items[0];
      setSelectedTemplateId(String(template.id));
      setForm((prev) => ({
        ...prev,
        title: template.template_name || "",
        ...buildBriefDraft(template),
      }));
    }
  }

  async function loadProjects(nextGroupId = groupFilter) {
    const data = await readJson(
      await authFetch(`/api/agent-flow/projects?group_id=${encodeURIComponent(nextGroupId)}`, { cache: "no-store" })
    );
    setProjects(data.items || []);
  }

  async function loadSummary(nextGroupId = groupFilter) {
    const data = await readJson(
      await authFetch(
        `/api/agent-flow/summary?group_id=${encodeURIComponent(nextGroupId)}`,
        { cache: "no-store" }
      )
    );
    setSummary(data);
  }

  async function loadRuns(nextStatus = statusFilter, nextLimit = pageSize, nextGroupId = groupFilter) {
    const data = await readJson(
      await authFetch(
        `/api/agent-flow/runs?status=${encodeURIComponent(nextStatus)}&group_id=${encodeURIComponent(nextGroupId)}&limit=${encodeURIComponent(nextLimit)}`,
        { cache: "no-store" }
      )
    );
    const items = data.items || [];
    setRuns(items);
    if (items.length === 0) {
      setSelectedRunId("");
      return;
    }
    setSelectedRunId((prev) => {
      const matched = items.find((item) => String(item.id) === String(prev));
      return matched ? String(matched.id) : String(items[0].id);
    });
  }

  async function loadRunDetails(runId) {
    if (!runId) {
      setStages([]);
      setAssets([]);
      setAssetBundle(null);
      return;
    }
    const [stagesData, assetsData] = await Promise.all([
      readJson(await authFetch(`/api/agent-flow/runs/${runId}/stages`, { cache: "no-store" })),
      readJson(await authFetch(`/api/agent-flow/runs/${runId}/assets`, { cache: "no-store" })),
    ]);
    setStages(stagesData.items || []);
    setAssets(assetsData.items || []);
    setAssetBundle(assetsData.bundle || null);
  }

  async function reloadAll(nextStatus = statusFilter, nextLimit = pageSize, nextGroupId = groupFilter) {
    setMessage("正在刷新 AI 文案工作流...");
    try {
      await Promise.all([
        loadGroups(),
        loadWorkers(),
        loadTemplates(nextGroupId),
        loadProjects(nextGroupId),
        loadSummary(nextGroupId),
        loadRuns(nextStatus, nextLimit, nextGroupId),
      ]);
      setMessage("AI 文案工作流已刷新");
    } catch (error) {
      setMessage(error.message || "刷新工作流失败");
    }
  }

  useEffect(() => {
    reloadAll("", "20", "");
  }, []);

  useEffect(() => {
    loadRunDetails(selectedRunId).catch((error) => setMessage(error.message || "加载运行详情失败"));
  }, [selectedRunId]);

  function applyTemplate(templateId) {
    setSelectedTemplateId(templateId);
    const template = templates.find((item) => String(item.id) === String(templateId));
    if (!template) {
      return;
    }
    setForm((prev) => ({
      ...prev,
      title: template.template_name || prev.title,
      ...buildBriefDraft(template),
    }));
  }

  async function createRun(event) {
    event.preventDefault();
    if (!selectedTemplate) {
      setMessage("当前没有可用模板");
      return;
    }
    setBusy("create");
    setMessage("正在创建工作流运行...");
    try {
      const data = await readJson(
        await authFetch("/api/agent-flow/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            template_id: selectedTemplate.id,
            template_version_id: selectedTemplate.current_version_id,
            group_id: form.group_id ? Number(form.group_id) : null,
            title: form.title,
            priority: Number(form.priority || 100),
            run_type: "single",
            source_mode: "manual",
            platform_targets: [form.platform],
            brief_payload: normalizeBriefPayload(form),
            project_id: form.project_id ? Number(form.project_id) : null,
          }),
        })
      );
      setMessage(`工作流运行已创建：#${data.item.id} ${data.item.title}`);
      await reloadAll(statusFilter, pageSize, groupFilter);
      setSelectedRunId(String(data.item.id));
    } catch (error) {
      setMessage(error.message || "创建工作流运行失败");
    } finally {
      setBusy("");
    }
  }

  async function retryRun(run) {
    setBusy(`retry-${run.id}`);
    setMessage(`正在重试运行 #${run.id}...`);
    try {
      const data = await readJson(
        await authFetch(`/api/agent-flow/runs/${run.id}/retry`, {
          method: "POST",
        })
      );
      setMessage(`运行已重新入队：#${data.item.id}`);
      await reloadAll(statusFilter, pageSize, groupFilter);
      setSelectedRunId(String(run.id));
    } catch (error) {
      setMessage(error.message || "重试运行失败");
    } finally {
      setBusy("");
    }
  }

  async function pushToPublishCenter(run) {
    if (!run?.bundle?.id) {
      setMessage("当前运行还没有可用资产包");
      return;
    }
    setBusy(`publish-${run.id}`);
    setMessage(`正在把运行 #${run.id} 推送到发布中心...`);
    try {
      const data = await readJson(
        await authFetch(`/api/agent-flow/asset-bundles/${run.bundle.id}/push-publish-center`, {
          method: "POST",
        })
      );
      if (data.draft) {
        setStoredPublishDraft(data.draft);
      }
      setMessage(`运行 #${run.id} 已推送到发布中心草稿`);
      router.push("/publish");
    } catch (error) {
      setMessage(error.message || "推送发布中心失败");
    } finally {
      setBusy("");
    }
  }

  const summaryCards = [
    {
      label: "工作流运行",
      value: String(summary.total || 0),
      hint: "当前工作流总量",
      ok: true,
    },
    {
      label: "待处理",
      value: String(summary.pending || 0),
      hint: "等待 LLM Worker 领取",
      ok: (summary.pending || 0) >= 0,
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
      description="先把工作台闭环跑通：模板驱动创建运行、阶段可见、产物沉淀、结果推送发布中心。"
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
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={() => router.push("/agent-flow/templates")}
            >
              打开模板库
            </button>
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={() => router.push("/agent-flow/projects")}
            >
              打开项目库
            </button>
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={() => router.push("/agent-flow/settings")}
            >
              打开设置中心
            </button>
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
            <select
              style={{ ...inputStyle, width: 150 }}
              value={statusFilter}
              onChange={(event) => {
                const nextValue = event.target.value;
                setStatusFilter(nextValue);
                loadRuns(nextValue, pageSize, groupFilter).catch((error) => setMessage(error.message || "获取运行列表失败"));
              }}
            >
              <option value="">全部状态</option>
              {["pending", "queued", "running", "success", "failed", "cancelled"].map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
            <select
              style={{ ...inputStyle, width: 110 }}
              value={pageSize}
              onChange={(event) => {
                const nextValue = event.target.value;
                setPageSize(nextValue);
                loadRuns(statusFilter, nextValue, groupFilter).catch((error) => setMessage(error.message || "获取运行列表失败"));
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

      <div style={{ display: "grid", gridTemplateColumns: "minmax(360px, 520px) minmax(0, 1fr)", gap: 16 }}>
        <Section title="新建运行" hint="先按模板填写 Brief，再交给现有 agent_flow 执行链。">
          <form onSubmit={createRun} style={{ display: "grid", gap: 12 }}>
            <select
              style={inputStyle}
              value={selectedTemplateId}
              onChange={(event) => applyTemplate(event.target.value)}
            >
              <option value="">选择模板</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.template_name}
                </option>
              ))}
            </select>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 12 }}>
              <input
                style={inputStyle}
                value={form.title}
                onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
                placeholder="运行标题"
              />
              <input
                style={inputStyle}
                value={form.priority}
                onChange={(event) => setForm((prev) => ({ ...prev, priority: event.target.value }))}
                placeholder="优先级"
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <select
                style={inputStyle}
                value={form.group_id}
                onChange={(event) => setForm((prev) => ({ ...prev, group_id: event.target.value }))}
              >
                <option value="">归属账号组</option>
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.group_name}
                  </option>
                ))}
              </select>
              <select
                style={inputStyle}
                value={form.project_id}
                onChange={(event) => setForm((prev) => ({ ...prev, project_id: event.target.value }))}
              >
                <option value="">挂到项目（可留空）</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.project_name}
                  </option>
                ))}
              </select>
              <select
                style={inputStyle}
                value={form.platform}
                onChange={(event) => setForm((prev) => ({ ...prev, platform: event.target.value }))}
              >
                {(selectedTemplate?.platform_scope || ["tiktok"]).map((platform) => (
                  <option key={platform} value={platform}>
                    {platform}
                  </option>
                ))}
              </select>
            </div>
            <textarea
              style={{ ...inputStyle, minHeight: 90, resize: "vertical" }}
              value={form.topic_seed}
              onChange={(event) => setForm((prev) => ({ ...prev, topic_seed: event.target.value }))}
              placeholder="选题方向 / 业务背景 / 核心冲突"
            />
            <input
              style={inputStyle}
              value={form.goal}
              onChange={(event) => setForm((prev) => ({ ...prev, goal: event.target.value }))}
              placeholder="任务目标"
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <input
                style={inputStyle}
                value={form.audience}
                onChange={(event) => setForm((prev) => ({ ...prev, audience: event.target.value }))}
                placeholder="目标人群"
              />
              <input
                style={inputStyle}
                value={form.tone}
                onChange={(event) => setForm((prev) => ({ ...prev, tone: event.target.value }))}
                placeholder="文案风格"
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 160px", gap: 12 }}>
              <input
                style={inputStyle}
                value={form.language}
                onChange={(event) => setForm((prev) => ({ ...prev, language: event.target.value }))}
                placeholder="语言"
              />
              <input
                style={inputStyle}
                value={form.max_topics}
                onChange={(event) => setForm((prev) => ({ ...prev, max_topics: event.target.value }))}
                placeholder="候选数"
              />
              <label
                style={{
                  ...cardStyle,
                  padding: "10px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                <input
                  type="checkbox"
                  checked={Boolean(form.video_enabled)}
                  onChange={(event) => setForm((prev) => ({ ...prev, video_enabled: event.target.checked }))}
                />
                生成视频提示词
              </label>
            </div>
            <textarea
              style={{ ...inputStyle, minHeight: 80, resize: "vertical" }}
              value={form.reference_prompt}
              onChange={(event) => setForm((prev) => ({ ...prev, reference_prompt: event.target.value }))}
              placeholder="参考提示词"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 80, resize: "vertical" }}
              value={form.reference_copy}
              onChange={(event) => setForm((prev) => ({ ...prev, reference_copy: event.target.value }))}
              placeholder="参考文案"
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="submit" style={buttonStyle} disabled={busy === "create"}>
                {busy === "create" ? "创建中..." : "创建工作流运行"}
              </button>
              <button
                type="button"
                style={secondaryButtonStyle}
                onClick={() => {
                  if (!selectedTemplate) {
                    return;
                  }
                  setForm((prev) => ({
                    ...prev,
                    title: selectedTemplate.template_name || "",
                    ...buildBriefDraft(selectedTemplate),
                  }));
                  setMessage("已恢复当前模板默认参数");
                }}
              >
                恢复模板默认值
              </button>
            </div>
          </form>
        </Section>

        <Section
          title="运行详情"
          hint={selectedRun ? `当前选中运行 #${selectedRun.id}` : "点击下方运行列表查看阶段与资产"}
          action={
            selectedRun ? (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  onClick={() => router.push(`/agent-flow/runs/${selectedRun.id}`)}
                >
                  打开详情页
                </button>
                {selectedRun.bundle?.id ? (
                  <button
                    type="button"
                    style={secondaryButtonStyle}
                    onClick={() => router.push(`/agent-flow/assets/${selectedRun.bundle.id}`)}
                  >
                    打开资产包
                  </button>
                ) : null}
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  onClick={() => retryRun(selectedRun)}
                  disabled={!["failed", "cancelled", "success"].includes(selectedRun.status) || busy === `retry-${selectedRun.id}`}
                >
                  {busy === `retry-${selectedRun.id}` ? "重试中..." : "重试运行"}
                </button>
                <button
                  type="button"
                  style={buttonStyle}
                  onClick={() => pushToPublishCenter(selectedRun)}
                  disabled={selectedRun.status !== "success" || !selectedRun.bundle?.id || busy === `publish-${selectedRun.id}`}
                >
                  {busy === `publish-${selectedRun.id}` ? "推送中..." : "推送发布中心"}
                </button>
              </div>
            ) : null
          }
        >
          {!selectedRun ? (
            <div style={{ color: "#94a3b8", fontSize: 13 }}>当前还没有选中的运行。</div>
          ) : (
            <div style={{ display: "grid", gap: 14 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                  gap: 12,
                }}
              >
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>状态</div>
                  <div style={{ marginTop: 8 }}><StatusTag status={selectedRun.status} /></div>
                </div>
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>当前阶段</div>
                  <div style={{ marginTop: 8, fontSize: 13 }}>{selectedRun.current_stage_code || "-"}</div>
                </div>
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>模板</div>
                  <div style={{ marginTop: 8, fontSize: 13 }}>{selectedRun.template?.template_name || "-"}</div>
                </div>
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>资产包</div>
                  <div style={{ marginTop: 8, fontSize: 13 }}>{assetBundle?.bundle_code || selectedRun.bundle?.bundle_code || "-"}</div>
                </div>
              </div>

              <div style={{ display: "grid", gap: 10 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>阶段看板</div>
                <div style={{ display: "grid", gap: 8 }}>
                  {stages.map((stage) => (
                    <div
                      key={stage.id}
                      style={{
                        ...cardStyle,
                        padding: 12,
                        display: "grid",
                        gridTemplateColumns: "160px 110px 1fr 160px",
                        gap: 12,
                        alignItems: "center",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{stage.stage_name}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{stage.stage_code}</div>
                      </div>
                      <StatusTag status={stage.status} />
                      <div style={{ fontSize: 12, color: stage.error_message ? "#fca5a5" : "#94a3b8" }}>
                        {stage.error_message || stage.worker_code || stage.required_capability || "-"}
                      </div>
                      <div style={{ fontSize: 12, color: "#94a3b8" }}>
                        {stage.finished_at ? formatDate(stage.finished_at) : stage.started_at ? formatDate(stage.started_at) : "-"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: "grid", gap: 10 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>产物预览</div>
                <div style={{ display: "grid", gap: 8 }}>
                  {assets.length === 0 ? (
                    <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>
                      当前运行还没有可展示的资产。
                    </div>
                  ) : (
                    assets.map((asset) => (
                      <div key={asset.id} style={{ ...cardStyle, padding: 12 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 600 }}>{asset.title || asset.asset_type}</div>
                            <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{asset.asset_type}</div>
                          </div>
                          <div style={{ fontSize: 12, color: "#94a3b8" }}>{asset.mime_type || "text/plain"}</div>
                        </div>
                        <pre
                          style={{
                            margin: 0,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            fontSize: 12,
                            lineHeight: 1.6,
                            color: "#cbd5e1",
                          }}
                        >
                          {renderAssetPreview(asset)}
                        </pre>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </Section>
      </div>

      <Section
        title="最近运行"
        hint="工作台先以单页承接，模板、阶段、资产和推送结果都从这里汇总。"
        action={<div style={{ fontSize: 12, color: "#94a3b8" }}>共 {summary.total || 0} 条</div>}
      >
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                <th style={tableHeadStyle}>运行</th>
                <th style={{ ...tableHeadStyle, width: 120 }}>状态</th>
                <th style={{ ...tableHeadStyle, width: 150 }}>当前阶段</th>
                <th style={{ ...tableHeadStyle, width: 220 }}>资产包</th>
                <th style={{ ...tableHeadStyle, width: 160 }}>更新时间</th>
                <th style={{ ...tableHeadStyle, width: 260 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                    当前筛选条件下还没有工作流运行。
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr key={run.id} style={{ background: String(run.id) === String(selectedRunId) ? "rgba(79,70,229,.08)" : "transparent" }}>
                    <td style={tableCellStyle}>{run.id}</td>
                    <td style={tableCellStyle}>
                      <div style={{ fontWeight: 600 }}>{run.title}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                        {run.brief_payload?.topic_seed || "-"}
                      </div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                        模板：{run.template?.template_name || "-"} / 项目：{run.project_id || "-"} / 组：{run.group_id || "-"}
                      </div>
                    </td>
                    <td style={tableCellStyle}><StatusTag status={run.status} /></td>
                    <td style={tableCellStyle}>
                      <div>{run.current_stage_code || "-"}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                        Worker：{run.task?.assigned_worker_code || "-"}
                      </div>
                    </td>
                    <td style={tableCellStyle}>
                      <div>{run.bundle?.bundle_code || "-"}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                        {run.bundle?.summary || "-"}
                      </div>
                    </td>
                    <td style={tableCellStyle}>{formatDate(run.updated_at)}</td>
                    <td style={tableCellStyle}>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button
                          type="button"
                          style={secondaryButtonStyle}
                          onClick={() => setSelectedRunId(String(run.id))}
                        >
                          查看详情
                        </button>
                        <button
                          type="button"
                          style={secondaryButtonStyle}
                          onClick={() => router.push(`/agent-flow/runs/${run.id}`)}
                        >
                          独立页
                        </button>
                        {run.bundle?.id ? (
                          <button
                            type="button"
                            style={secondaryButtonStyle}
                            onClick={() => router.push(`/agent-flow/assets/${run.bundle.id}`)}
                          >
                            资产包
                          </button>
                        ) : null}
                        <button
                          type="button"
                          style={secondaryButtonStyle}
                          onClick={() => retryRun(run)}
                          disabled={!["failed", "cancelled", "success"].includes(run.status) || busy === `retry-${run.id}`}
                        >
                          {busy === `retry-${run.id}` ? "重试中..." : "重试"}
                        </button>
                        <button
                          type="button"
                          style={buttonStyle}
                          onClick={() => pushToPublishCenter(run)}
                          disabled={run.status !== "success" || !run.bundle?.id || busy === `publish-${run.id}`}
                        >
                          {busy === `publish-${run.id}` ? "推送中..." : "推送发布"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </DashboardShell>
  );
}
