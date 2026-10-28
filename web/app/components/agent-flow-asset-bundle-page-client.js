"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  DashboardShell,
  Section,
  SummaryCard,
  authFetch,
  buttonStyle,
  cardStyle,
  formatDate,
  inputStyle,
  readJson,
  secondaryButtonStyle,
} from "./dashboard-ui";

function StatusTag({ status }) {
  const palette = {
    ready: { bg: "rgba(34,197,94,.14)", border: "rgba(34,197,94,.35)", color: "#86efac" },
    draft: { bg: "rgba(148,163,184,.14)", border: "rgba(148,163,184,.35)", color: "#cbd5e1" },
    published: { bg: "rgba(16,185,129,.14)", border: "rgba(16,185,129,.35)", color: "#6ee7b7" },
    archived: { bg: "rgba(100,116,139,.14)", border: "rgba(100,116,139,.35)", color: "#cbd5e1" },
    pushed: { bg: "rgba(16,185,129,.14)", border: "rgba(16,185,129,.35)", color: "#6ee7b7" },
    failed: { bg: "rgba(239,68,68,.14)", border: "rgba(239,68,68,.35)", color: "#fca5a5" },
  };
  const current = palette[status] || palette.draft;
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

export default function AgentFlowAssetBundlePageClient({ bundleId }) {
  const [bundle, setBundle] = useState(null);
  const [run, setRun] = useState(null);
  const [assets, setAssets] = useState([]);
  const [publishLinks, setPublishLinks] = useState([]);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [editDraft, setEditDraft] = useState({ title: "", content_text: "" });
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");

  const selectedAsset = useMemo(
    () => assets.find((item) => String(item.id) === String(selectedAssetId)) || null,
    [assets, selectedAssetId]
  );

  async function loadAll() {
    setMessage(`正在加载资产包 #${bundleId}...`);
    try {
      const data = await readJson(await authFetch(`/api/agent-flow/asset-bundles/${bundleId}`, { cache: "no-store" }));
      setBundle(data.bundle || null);
      setRun(data.run || null);
      const nextAssets = data.assets || [];
      setAssets(nextAssets);
      setPublishLinks(data.publish_links || []);
      setSelectedAssetId((prev) => {
        const matched = nextAssets.find((item) => String(item.id) === String(prev));
        return matched ? String(matched.id) : String(nextAssets[0]?.id || "");
      });
      setMessage(`资产包 #${bundleId} 已加载`);
    } catch (error) {
      setMessage(error.message || "加载资产包失败");
    }
  }

  useEffect(() => {
    loadAll();
  }, [bundleId]);

  useEffect(() => {
    if (!selectedAsset) {
      setEditDraft({ title: "", content_text: "" });
      return;
    }
    setEditDraft({
      title: selectedAsset.title || "",
      content_text: selectedAsset.content_text || "",
    });
  }, [selectedAssetId, selectedAsset]);

  async function selectAsset(asset) {
    if (!run?.id) {
      return;
    }
    setBusy(`select-${asset.id}`);
    setMessage(`正在设为主版本：${asset.title || asset.asset_type}...`);
    try {
      await readJson(
        await authFetch(`/api/agent-flow/runs/${run.id}/assets/select`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ asset_id: asset.id }),
        })
      );
      await loadAll();
    } catch (error) {
      setMessage(error.message || "设置主版本失败");
    } finally {
      setBusy("");
    }
  }

  async function saveAsset() {
    if (!selectedAsset) {
      return;
    }
    setBusy(`save-${selectedAsset.id}`);
    setMessage(`正在保存资产 #${selectedAsset.id}...`);
    try {
      await readJson(
        await authFetch(`/api/agent-flow/assets/${selectedAsset.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: editDraft.title,
            content_text: editDraft.content_text,
          }),
        })
      );
      await loadAll();
    } catch (error) {
      setMessage(error.message || "保存资产失败");
    } finally {
      setBusy("");
    }
  }

  const cards = [
    { label: "资产包状态", value: bundle?.status || "-", hint: bundle?.bundle_name || "当前资产包", ok: Boolean(bundle) },
    { label: "资产数量", value: String(assets.length), hint: "本次沉淀结果", ok: assets.length > 0 },
    { label: "推送次数", value: String(publishLinks.length), hint: "发布中心推送记录", ok: publishLinks.length > 0 },
    { label: "运行编号", value: run?.run_code || "-", hint: "来源运行", ok: Boolean(run?.run_code) },
  ];

  return (
    <DashboardShell
      title={`资产包详情 #${bundleId}`}
      description="这里专门整理脚本、提示词、发布稿和视频结果，做主版本选择与人工修订。"
      action={
        <div style={{ display: "grid", gap: 10, minWidth: "min(100%, 680px)" }}>
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
            {run?.id ? (
              <Link
                href={`/agent-flow/runs/${run.id}`}
                style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
              >
                返回运行详情
              </Link>
            ) : null}
            <button type="button" style={buttonStyle} onClick={loadAll}>
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
        {cards.map((item) => (
          <SummaryCard key={item.label} label={item.label} value={item.value} hint={item.hint} ok={item.ok} />
        ))}
      </section>

      {!bundle ? (
        <Section title="资产包详情" hint="当前没有可展示的数据。">
          <div style={{ color: "#94a3b8", fontSize: 13 }}>请确认资产包 ID 是否存在。</div>
        </Section>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(380px, 520px) minmax(0, 1fr)", gap: 16 }}>
            <Section title="资产列表" hint="这里可以切主版本，也能快速查看每个资产类型的候选项。">
              <div style={{ display: "grid", gap: 8 }}>
                {assets.length === 0 ? (
                  <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>
                    当前资产包还没有资产记录。
                  </div>
                ) : (
                  assets.map((asset) => (
                    <div
                      key={asset.id}
                      style={{
                        ...cardStyle,
                        padding: 12,
                        background: String(asset.id) === String(selectedAssetId) ? "rgba(79,70,229,.08)" : cardStyle.background,
                        cursor: "pointer",
                      }}
                      onClick={() => setSelectedAssetId(String(asset.id))}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 700 }}>{asset.title || asset.asset_type}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            类型：{asset.asset_type} / 角色：{asset.asset_role || "-"}
                          </div>
                        </div>
                        <div style={{ display: "grid", gap: 6, justifyItems: "end" }}>
                          <StatusTag status={asset.is_selected ? "ready" : "draft"} />
                          <button
                            type="button"
                            style={asset.is_selected ? secondaryButtonStyle : buttonStyle}
                            disabled={asset.is_selected || busy === `select-${asset.id}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              selectAsset(asset);
                            }}
                          >
                            {busy === `select-${asset.id}` ? "设置中..." : asset.is_selected ? "主版本" : "设为主版本"}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Section>

            <Section
              title="资产详情"
              hint={selectedAsset ? `当前资产：${selectedAsset.title || selectedAsset.asset_type}` : "点击左侧资产查看详情"}
            >
              {!selectedAsset ? (
                <div style={{ color: "#94a3b8", fontSize: 13 }}>当前还没有选中的资产。</div>
              ) : (
                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ ...cardStyle, padding: 12 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: 12 }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{selectedAsset.title || selectedAsset.asset_type}</div>
                        <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                          类型：{selectedAsset.asset_type} / 版本：#{selectedAsset.version_no || 1}
                        </div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          R2 Key：{selectedAsset.r2_key || "-"} / MIME：{selectedAsset.mime_type || "-"}
                        </div>
                      </div>
                      <div style={{ display: "grid", alignItems: "start", justifyItems: "end" }}>
                        <StatusTag status={selectedAsset.is_selected ? "ready" : "draft"} />
                      </div>
                    </div>
                  </div>

                  <div style={{ ...cardStyle, padding: 12, display: "grid", gap: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>手工修订</div>
                    <input
                      style={inputStyle}
                      value={editDraft.title}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, title: event.target.value }))}
                      placeholder="资产标题"
                    />
                    <textarea
                      style={{ ...inputStyle, minHeight: 220, resize: "vertical" }}
                      value={editDraft.content_text}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, content_text: event.target.value }))}
                      placeholder="资产文本内容"
                    />
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        style={buttonStyle}
                        disabled={busy === `save-${selectedAsset.id}`}
                        onClick={saveAsset}
                      >
                        {busy === `save-${selectedAsset.id}` ? "保存中..." : "保存修订"}
                      </button>
                      <button
                        type="button"
                        style={secondaryButtonStyle}
                        onClick={() =>
                          setEditDraft({
                            title: selectedAsset.title || "",
                            content_text: selectedAsset.content_text || "",
                          })
                        }
                      >
                        恢复当前内容
                      </button>
                    </div>
                  </div>

                  <div style={{ ...cardStyle, padding: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>结构化内容</div>
                    <PreviewText value={selectedAsset.content_json || {}} />
                  </div>
                </div>
              )}
            </Section>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 420px)", gap: 16 }}>
            <Section title="来源运行" hint="资产包始终挂到单次运行，方便回放与追溯。">
              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{run?.title || "-"}</div>
                <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                  运行编号：{run?.run_code || "-"} / 当前阶段：{run?.current_stage_code || "-"}
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                  创建时间：{formatDate(run?.created_at)} / 更新时间：{formatDate(run?.updated_at)}
                </div>
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
