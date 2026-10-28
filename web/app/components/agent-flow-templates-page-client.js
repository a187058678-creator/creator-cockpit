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

function JsonPreview({ value }) {
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
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

export default function AgentFlowTemplatesPageClient() {
  const [groups, setGroups] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [versions, setVersions] = useState([]);
  const [settings, setSettings] = useState({ model_presets: [], stage_chain_presets: [] });
  const [groupFilter, setGroupFilter] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [presetForm, setPresetForm] = useState({ model_presets: "", stage_chain_presets: "" });
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");

  const selectedTemplate = useMemo(
    () => templates.find((item) => String(item.id) === String(selectedTemplateId)) || null,
    [templates, selectedTemplateId]
  );
  const selectedVersion = useMemo(
    () => versions.find((item) => String(item.id) === String(selectedVersionId)) || null,
    [versions, selectedVersionId]
  );

  async function loadGroups() {
    const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
    setGroups(data.items || []);
  }

  async function loadTemplates(nextGroupId = groupFilter) {
    const data = await readJson(
      await authFetch(`/api/agent-flow/templates?group_id=${encodeURIComponent(nextGroupId)}`, {
        cache: "no-store",
      })
    );
    const items = data.items || [];
    setTemplates(items);
    setSelectedTemplateId((prev) => {
      const matched = items.find((item) => String(item.id) === String(prev));
      return matched ? String(matched.id) : String(items[0]?.id || "");
    });
  }

  async function loadSettings() {
    const data = await readJson(await authFetch("/api/agent-flow/settings/presets", { cache: "no-store" }));
    const nextSettings = {
      model_presets: data.model_presets || [],
      stage_chain_presets: data.stage_chain_presets || [],
    };
    setSettings(nextSettings);
    setPresetForm((prev) => ({
      model_presets: prev.model_presets || nextSettings.model_presets[0]?.code || "",
      stage_chain_presets: prev.stage_chain_presets || nextSettings.stage_chain_presets[0]?.code || "",
    }));
  }

  async function loadVersions(templateId = selectedTemplateId) {
    if (!templateId) {
      setVersions([]);
      setSelectedVersionId("");
      return;
    }
    const data = await readJson(
      await authFetch(`/api/agent-flow/templates/${templateId}/versions`, { cache: "no-store" })
    );
    const items = data.items || [];
    setVersions(items);
    setSelectedVersionId((prev) => {
      const matched = items.find((item) => String(item.id) === String(prev));
      return matched ? String(matched.id) : String(items[0]?.id || "");
    });
  }

  async function reload(nextGroupId = groupFilter) {
    setMessage("正在刷新模板库...");
    try {
      await Promise.all([loadGroups(), loadTemplates(nextGroupId), loadSettings()]);
      setMessage("模板库已刷新");
    } catch (error) {
      setMessage(error.message || "获取模板库失败");
    }
  }

  useEffect(() => {
    reload("");
  }, []);

  useEffect(() => {
    loadVersions(selectedTemplateId).catch((error) => setMessage(error.message || "获取版本列表失败"));
  }, [selectedTemplateId]);

  async function publishVersion(versionId) {
    setBusy(`publish-${versionId}`);
    setMessage(`正在切换版本 #${versionId}...`);
    try {
      const data = await readJson(
        await authFetch(`/api/agent-flow/template-versions/${versionId}/publish`, { method: "POST" })
      );
      setMessage(`已切换当前版本：${data.item.current_version?.version_name || "-"}`);
      await loadTemplates(groupFilter);
      await loadVersions(selectedTemplateId);
    } catch (error) {
      setMessage(error.message || "切换模板版本失败");
    } finally {
      setBusy("");
    }
  }

  async function applyPreset(presetType) {
    if (!selectedVersionId) {
      setMessage("请先选择模板版本");
      return;
    }
    const presetCode = presetForm[presetType];
    if (!presetCode) {
      setMessage("请先选择预设");
      return;
    }
    setBusy(`preset-${presetType}`);
    setMessage(`正在应用预设：${presetCode}...`);
    try {
      await readJson(
        await authFetch(`/api/agent-flow/template-versions/${selectedVersionId}/apply-preset`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset_type: presetType, preset_code: presetCode }),
        })
      );
      await loadVersions(selectedTemplateId);
      await loadTemplates(groupFilter);
      setMessage(`已应用预设：${presetCode}`);
    } catch (error) {
      setMessage(error.message || "应用预设失败");
    } finally {
      setBusy("");
    }
  }

  const cards = [
    { label: "模板总数", value: String(templates.length), hint: "当前可用模板", ok: true },
    {
      label: "当前模板版本",
      value: selectedTemplate?.current_version?.version_name || "-",
      hint: "当前选中模板",
      ok: Boolean(selectedTemplate),
    },
    {
      label: "版本数量",
      value: String(versions.length),
      hint: "当前模板全部版本",
      ok: versions.length > 0,
    },
  ];

  return (
    <DashboardShell
      title="AI文案模板库"
      description="这里专门看模板、版本和结构定义，不再和工作台创建运行混在一起。"
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
                reload(nextValue);
              }}
            >
              <option value="">全部账号组</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.group_name}
                </option>
              ))}
            </select>
            <Link href="/agent-flow" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
              返回工作台
            </Link>
            <button type="button" style={buttonStyle} onClick={() => reload(groupFilter)}>
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

      <div style={{ display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(360px, 520px)", gap: 16 }}>
        <Section title="模板列表" hint="先展示当前启用版本和结构摘要，编辑能力后面再补。">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                  <th style={tableHeadStyle}>模板</th>
                  <th style={{ ...tableHeadStyle, width: 120 }}>分类</th>
                  <th style={{ ...tableHeadStyle, width: 130 }}>当前版本</th>
                  <th style={{ ...tableHeadStyle, width: 160 }}>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {templates.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      当前还没有模板记录。
                    </td>
                  </tr>
                ) : (
                  templates.map((template) => (
                    <tr
                      key={template.id}
                      onClick={() => setSelectedTemplateId(String(template.id))}
                      style={{
                        cursor: "pointer",
                        background: String(template.id) === String(selectedTemplateId) ? "rgba(79,70,229,.08)" : "transparent",
                      }}
                    >
                      <td style={tableCellStyle}>{template.id}</td>
                      <td style={tableCellStyle}>
                        <div style={{ fontWeight: 600 }}>{template.template_name}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{template.template_code}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{template.remark || "-"}</div>
                      </td>
                      <td style={tableCellStyle}>{template.category || "-"}</td>
                      <td style={tableCellStyle}>
                        {template.current_version?.version_name || "-"}
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          #{template.current_version?.version_no || "-"}
                        </div>
                      </td>
                      <td style={tableCellStyle}>{formatDate(template.updated_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>

        <Section
          title="模板详情"
          hint={selectedTemplate ? `当前选中模板 #${selectedTemplate.id}` : "点击左侧模板查看结构"}
          action={
            selectedTemplate ? (
              <Link
                href="/agent-flow"
                style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
              >
                去工作台使用
              </Link>
            ) : null
          }
        >
          {!selectedTemplate ? (
            <div style={{ color: "#94a3b8", fontSize: 13 }}>当前还没有选中的模板。</div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{selectedTemplate.template_name}</div>
                <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                  平台范围：{(selectedTemplate.platform_scope || []).join(" / ") || "-"}
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                  风格：{selectedTemplate.style_type || "-"} / 状态：{selectedTemplate.status || "-"}
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                  当前版本：{selectedTemplate.current_version?.version_name || "-"} / ID：{selectedTemplate.current_version_id || "-"}
                </div>
              </div>

              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 8, alignItems: "center" }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>版本列表</div>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>共 {versions.length} 个版本</div>
                </div>
                <div style={{ display: "grid", gap: 8 }}>
                  {versions.length === 0 ? (
                    <div style={{ fontSize: 12, color: "#94a3b8" }}>当前模板还没有版本记录。</div>
                  ) : (
                    versions.map((version) => {
                      const isCurrent = String(version.id) === String(selectedTemplate.current_version_id);
                      const isSelected = String(version.id) === String(selectedVersionId);
                      return (
                        <div
                          key={version.id}
                          style={{
                            ...cardStyle,
                            padding: 10,
                            background: isSelected ? "rgba(79,70,229,.08)" : cardStyle.background,
                            cursor: "pointer",
                          }}
                          onClick={() => setSelectedVersionId(String(version.id))}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 700 }}>{version.version_name}</div>
                              <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                                版本号：#{version.version_no} / 创建时间：{formatDate(version.created_at)}
                              </div>
                            </div>
                            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                              <span style={{ fontSize: 12, color: isCurrent ? "#86efac" : "#94a3b8" }}>
                                {isCurrent ? "当前版本" : version.is_published ? "已发布" : "草稿"}
                              </span>
                              <button
                                type="button"
                                style={isCurrent ? secondaryButtonStyle : buttonStyle}
                                disabled={isCurrent || busy === `publish-${version.id}`}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  publishVersion(version.id);
                                }}
                              >
                                {busy === `publish-${version.id}` ? "切换中..." : isCurrent ? "已启用" : "设为当前"}
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>快速应用预设</div>
                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 8 }}>
                    <select
                      style={inputStyle}
                      value={presetForm.model_presets}
                      onChange={(event) =>
                        setPresetForm((prev) => ({ ...prev, model_presets: event.target.value }))
                      }
                    >
                      <option value="">选择模型预设</option>
                      {settings.model_presets.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      style={buttonStyle}
                      disabled={!selectedVersion || busy === "preset-model_presets"}
                      onClick={() => applyPreset("model_presets")}
                    >
                      {busy === "preset-model_presets" ? "应用中..." : "应用模型"}
                    </button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 8 }}>
                    <select
                      style={inputStyle}
                      value={presetForm.stage_chain_presets}
                      onChange={(event) =>
                        setPresetForm((prev) => ({ ...prev, stage_chain_presets: event.target.value }))
                      }
                    >
                      <option value="">选择阶段链预设</option>
                      {settings.stage_chain_presets.map((item) => (
                        <option key={item.code} value={item.code}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      style={buttonStyle}
                      disabled={!selectedVersion || busy === "preset-stage_chain_presets"}
                      onClick={() => applyPreset("stage_chain_presets")}
                    >
                      {busy === "preset-stage_chain_presets" ? "应用中..." : "应用阶段链"}
                    </button>
                  </div>
                </div>
              </div>

              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
                  Brief Schema {selectedVersion ? `· ${selectedVersion.version_name}` : ""}
                </div>
                <JsonPreview value={selectedVersion?.brief_schema || selectedTemplate.current_version?.brief_schema} />
              </div>

              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Stage Schema</div>
                <JsonPreview value={selectedVersion?.stage_schema || selectedTemplate.current_version?.stage_schema} />
              </div>

              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>默认模型配置</div>
                <JsonPreview value={selectedVersion?.default_model_config || selectedTemplate.current_version?.default_model_config} />
              </div>
            </div>
          )}
        </Section>
      </div>
    </DashboardShell>
  );
}
