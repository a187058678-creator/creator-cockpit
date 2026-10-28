"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  DashboardShell,
  Section,
  SummaryCard,
  authFetch,
  buttonStyle,
  cardStyle,
  formatDate,
  readJson,
  secondaryButtonStyle,
  setStoredPublishDraft,
} from "./dashboard-ui";

function StatusTag({ status }) {
  const palette = {
    success: { bg: "rgba(34,197,94,.14)", border: "rgba(34,197,94,.35)", color: "#86efac" },
    running: { bg: "rgba(59,130,246,.14)", border: "rgba(59,130,246,.35)", color: "#93c5fd" },
    queued: { bg: "rgba(245,158,11,.14)", border: "rgba(245,158,11,.35)", color: "#fcd34d" },
    pending: { bg: "rgba(148,163,184,.14)", border: "rgba(148,163,184,.35)", color: "#cbd5e1" },
    failed: { bg: "rgba(239,68,68,.14)", border: "rgba(239,68,68,.35)", color: "#fca5a5" },
    cancelled: { bg: "rgba(100,116,139,.14)", border: "rgba(100,116,139,.35)", color: "#cbd5e1" },
    published: { bg: "rgba(16,185,129,.14)", border: "rgba(16,185,129,.35)", color: "#6ee7b7" },
    pushed: { bg: "rgba(16,185,129,.14)", border: "rgba(16,185,129,.35)", color: "#6ee7b7" },
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

function PreviewText({ value }) {
  return (
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
      {typeof value === "string" ? value : JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

export default function AgentFlowRunDetailPageClient({ runId }) {
  const router = useRouter();
  const [run, setRun] = useState(null);
  const [stages, setStages] = useState([]);
  const [selectedStageId, setSelectedStageId] = useState("");
  const [assets, setAssets] = useState([]);
  const [bundle, setBundle] = useState(null);
  const [publishLinks, setPublishLinks] = useState([]);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");

  async function loadAll() {
    setMessage(`正在加载运行 #${runId}...`);
    try {
      const runData = await readJson(await authFetch(`/api/agent-flow/runs/${runId}`, { cache: "no-store" }));
      setRun(runData.item || null);
      const [stagesData, assetsData, publishData] = await Promise.all([
        readJson(await authFetch(`/api/agent-flow/runs/${runId}/stages`, { cache: "no-store" })),
        readJson(await authFetch(`/api/agent-flow/runs/${runId}/assets`, { cache: "no-store" })),
        runData.item?.bundle?.id
          ? readJson(
              await authFetch(`/api/agent-flow/asset-bundles/${runData.item.bundle.id}/publish-links`, {
                cache: "no-store",
              })
            )
          : Promise.resolve({ items: [] }),
      ]);
      setStages(stagesData.items || []);
      setSelectedStageId((prev) => {
        const items = stagesData.items || [];
        const matched = items.find((item) => String(item.id) === String(prev));
        return matched ? String(matched.id) : String(items[0]?.id || "");
      });
      setAssets(assetsData.items || []);
      setBundle(assetsData.bundle || runData.item?.bundle || null);
      setPublishLinks(publishData.items || []);
      setMessage(`运行 #${runId} 已加载`);
    } catch (error) {
      setMessage(error.message || "加载运行详情失败");
    }
  }

  const selectedStage = stages.find((item) => String(item.id) === String(selectedStageId)) || null;

  useEffect(() => {
    loadAll();
  }, [runId]);

  async function retryRun() {
    setBusy("retry");
    setMessage(`正在重试运行 #${runId}...`);
    try {
      await readJson(await authFetch(`/api/agent-flow/runs/${runId}/retry`, { method: "POST" }));
      await loadAll();
    } catch (error) {
      setMessage(error.message || "重试运行失败");
    } finally {
      setBusy("");
    }
  }

  async function pushToPublishCenter() {
    if (!bundle?.id) {
      setMessage("当前运行还没有可用资产包");
      return;
    }
    setBusy("publish");
    setMessage(`正在把运行 #${runId} 推送到发布中心...`);
    try {
      const data = await readJson(
        await authFetch(`/api/agent-flow/asset-bundles/${bundle.id}/push-publish-center`, {
          method: "POST",
        })
      );
      if (data.draft) {
        setStoredPublishDraft(data.draft);
      }
      router.push("/publish");
    } catch (error) {
      setMessage(error.message || "推送发布中心失败");
    } finally {
      setBusy("");
    }
  }

  async function retryStage(stage) {
    setBusy(`stage-${stage.id}`);
    setMessage(`正在重跑阶段 ${stage.stage_name}...`);
    try {
      await readJson(await authFetch(`/api/agent-flow/run-stages/${stage.id}/retry`, { method: "POST" }));
      await loadAll();
    } catch (error) {
      setMessage(error.message || "单阶段重跑失败");
    } finally {
      setBusy("");
    }
  }

  const cards = [
    { label: "运行状态", value: run?.status || "-", hint: run?.title || "当前运行", ok: Boolean(run) },
    { label: "当前阶段", value: run?.current_stage_code || "-", hint: "阶段调度视图", ok: Boolean(run?.current_stage_code) },
    { label: "阶段数量", value: String(stages.length), hint: "当前运行阶段", ok: stages.length > 0 },
    { label: "资产数量", value: String(assets.length), hint: "当前沉淀结果", ok: assets.length > 0 },
  ];

  return (
    <DashboardShell
      title={`运行详情 #${runId}`}
      description="这里专门看单次运行的回放、阶段、资产和推送记录。"
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
            }}
          >
            当前消息：{message}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <Link href="/agent-flow" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
              返回工作台
            </Link>
            {bundle?.id ? (
              <Link
                href={`/agent-flow/assets/${bundle.id}`}
                style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
              >
                打开资产包
              </Link>
            ) : null}
            <button type="button" style={secondaryButtonStyle} onClick={loadAll}>
              刷新详情
            </button>
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={retryRun}
              disabled={!["failed", "cancelled", "success"].includes(run?.status) || busy === "retry"}
            >
              {busy === "retry" ? "重试中..." : "重试运行"}
            </button>
            <button
              type="button"
              style={buttonStyle}
              onClick={pushToPublishCenter}
              disabled={run?.status !== "success" || !bundle?.id || busy === "publish"}
            >
              {busy === "publish" ? "推送中..." : "推送发布中心"}
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
        {cards.map((item) => (
          <SummaryCard key={item.label} label={item.label} value={item.value} hint={item.hint} ok={item.ok} />
        ))}
      </section>

      {!run ? (
        <Section title="运行详情" hint="当前没有可展示的数据。">
          <div style={{ color: "#94a3b8", fontSize: 13 }}>请确认运行 ID 是否存在。</div>
        </Section>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(360px, 460px) minmax(0, 1fr)", gap: 16 }}>
            <Section title="基础信息" hint="这里集中看运行、模板和 Worker 承接关系。">
              <div style={{ display: "grid", gap: 10 }}>
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{run.title}</div>
                  <div style={{ marginTop: 8 }}>
                    <StatusTag status={run.status} />
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                    模板：{run.template?.template_name || "-"} / 版本：{run.template?.current_version?.version_name || "-"}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                    账号组：{run.group_id || "-"} / Worker：{run.task?.assigned_worker_code || "-"}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                    创建时间：{formatDate(run.created_at)} / 更新时间：{formatDate(run.updated_at)}
                  </div>
                </div>

                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Brief</div>
                  <PreviewText value={run.brief_payload} />
                </div>
              </div>
            </Section>

            <Section
              title="阶段时间线"
              hint="可以切到单个阶段查看输入输出，也可以从该阶段重新排队执行。"
            >
              <div style={{ display: "grid", gap: 8 }}>
                {stages.map((stage) => (
                  <div
                    key={stage.id}
                    style={{
                      ...cardStyle,
                      padding: 12,
                      display: "grid",
                      gridTemplateColumns: "180px 110px 1fr 170px 180px",
                      gap: 12,
                      alignItems: "center",
                      background: String(stage.id) === String(selectedStageId) ? "rgba(79,70,229,.08)" : cardStyle.background,
                      cursor: "pointer",
                    }}
                    onClick={() => setSelectedStageId(String(stage.id))}
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
                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        style={secondaryButtonStyle}
                        disabled={stage.stage_code === "brief_collect" || busy === `stage-${stage.id}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          retryStage(stage);
                        }}
                      >
                        {busy === `stage-${stage.id}` ? "重跑中..." : "单阶段重跑"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          </div>

          <Section
            title="输入输出对照"
            hint={selectedStage ? `当前阶段：${selectedStage.stage_name}` : "点击上方阶段查看输入输出"}
            action={
              selectedStage ? (
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  disabled={selectedStage.stage_code === "brief_collect" || busy === `stage-${selectedStage.id}`}
                  onClick={() => retryStage(selectedStage)}
                >
                  {busy === `stage-${selectedStage.id}` ? "重跑中..." : "从该阶段重跑"}
                </button>
              ) : null
            }
          >
            {!selectedStage ? (
              <div style={{ color: "#94a3b8", fontSize: 13 }}>当前还没有选中的阶段。</div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 16 }}>
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>输入</div>
                  <PreviewText value={selectedStage.input_payload || {}} />
                </div>
                <div style={{ ...cardStyle, padding: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>输出</div>
                  <PreviewText value={selectedStage.output_payload || {}} />
                </div>
              </div>
            )}
          </Section>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 420px)", gap: 16 }}>
            <Section title="资产包" hint={bundle ? `资产包：${bundle.bundle_code}` : "当前还没有资产包"}>
              <div style={{ display: "grid", gap: 8 }}>
                {bundle?.id ? (
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <Link
                      href={`/agent-flow/assets/${bundle.id}`}
                      style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                    >
                      去资产包详情页
                    </Link>
                  </div>
                ) : null}
                {assets.length === 0 ? (
                  <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>
                    当前运行还没有沉淀资产。
                  </div>
                ) : (
                  assets.map((asset) => (
                    <div key={asset.id} style={{ ...cardStyle, padding: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 700 }}>{asset.title || asset.asset_type}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{asset.asset_type}</div>
                        </div>
                        <div style={{ fontSize: 12, color: "#94a3b8" }}>
                          {asset.mime_type || asset.r2_key || "text/plain"}
                        </div>
                      </div>
                      <PreviewText value={asset.content_text || asset.content_json} />
                    </div>
                  ))
                )}
              </div>
            </Section>

            <Section title="推送记录" hint="这里看资产包推到发布中心的历史。">
              <div style={{ display: "grid", gap: 8 }}>
                {publishLinks.length === 0 ? (
                  <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>
                    当前还没有推送记录。
                  </div>
                ) : (
                  publishLinks.map((item) => (
                    <div key={item.id} style={{ ...cardStyle, padding: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{item.title_text || "未命名推送"}</div>
                        <StatusTag status={item.status} />
                      </div>
                      <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                        平台：{item.platform || "-"} / 推送时间：{formatDate(item.pushed_at || item.created_at)}
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <PreviewText value={item.body_text || "-"} />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Section>
          </div>
        </>
      )}
    </DashboardShell>
  );
}
