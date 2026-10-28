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
  secondaryButtonStyle,
  readJson,
} from "./dashboard-ui";

const CATEGORY_MAP = {
  style_bibles: "风格圣经库",
  character_bibles: "角色圣经库",
  shot_bibles: "镜头圣经库",
  model_presets: "模型预设",
  stage_chain_presets: "阶段链预设",
  platform_presets: "平台预设",
};

function Preview({ value }) {
  return (
    <pre
      style={{
        margin: 0,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        fontSize: 12,
        lineHeight: 1.65,
        color: "#cbd5e1",
      }}
    >
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

export default function AgentFlowSettingsPageClient() {
  const [catalog, setCatalog] = useState({
    style_bibles: [],
    character_bibles: [],
    shot_bibles: [],
    model_presets: [],
    stage_chain_presets: [],
    platform_presets: [],
  });
  const [activeCategory, setActiveCategory] = useState("style_bibles");
  const [selectedCode, setSelectedCode] = useState("");
  const [message, setMessage] = useState("已就绪");

  const activeItems = catalog[activeCategory] || [];
  const selectedItem = useMemo(
    () => activeItems.find((item) => String(item.code) === String(selectedCode)) || activeItems[0] || null,
    [activeItems, selectedCode]
  );

  async function loadCatalog() {
    setMessage("正在加载设置中心预设...");
    try {
      const data = await readJson(await authFetch("/api/agent-flow/settings/presets", { cache: "no-store" }));
      setCatalog({
        style_bibles: data.style_bibles || [],
        character_bibles: data.character_bibles || [],
        shot_bibles: data.shot_bibles || [],
        model_presets: data.model_presets || [],
        stage_chain_presets: data.stage_chain_presets || [],
        platform_presets: data.platform_presets || [],
      });
      setMessage("设置中心已加载");
    } catch (error) {
      setMessage(error.message || "加载设置中心失败");
    }
  }

  useEffect(() => {
    loadCatalog();
  }, []);

  useEffect(() => {
    setSelectedCode(activeItems[0]?.code || "");
  }, [activeCategory]);

  const cards = [
    { label: "风格圣经", value: String(catalog.style_bibles.length), hint: "控制语言气质", ok: catalog.style_bibles.length > 0 },
    { label: "角色圣经", value: String(catalog.character_bibles.length), hint: "控制人设与口吻", ok: catalog.character_bibles.length > 0 },
    { label: "镜头圣经", value: String(catalog.shot_bibles.length), hint: "控制视觉表达", ok: catalog.shot_bibles.length > 0 },
    { label: "模型/阶段预设", value: String(catalog.model_presets.length + catalog.stage_chain_presets.length), hint: "跑批配置模板", ok: true },
  ];

  return (
    <DashboardShell
      title="AI文案设置中心"
      description="这里先放轻量配置面板：风格库、角色库、镜头库、模型预设、阶段链预设。第一期先看和选，不提前做重编辑器。"
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
            <Link href="/agent-flow/templates" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
              打开模板库
            </Link>
            <button type="button" style={buttonStyle} onClick={loadCatalog}>
              刷新页面
            </button>
          </div>
        </div>
      }
    >
      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
        {cards.map((item) => (
          <SummaryCard key={item.label} label={item.label} value={item.value} hint={item.hint} ok={item.ok} />
        ))}
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "220px minmax(320px, 420px) minmax(0, 1fr)", gap: 16 }}>
        <Section title="分类导航" hint="先按配置类型切换。">
          <div style={{ display: "grid", gap: 8 }}>
            {Object.entries(CATEGORY_MAP).map(([key, label]) => (
              <button
                key={key}
                type="button"
                style={{
                  ...(activeCategory === key ? buttonStyle : secondaryButtonStyle),
                  textAlign: "left",
                  justifyContent: "flex-start",
                }}
                onClick={() => setActiveCategory(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </Section>

        <Section title={CATEGORY_MAP[activeCategory]} hint="左侧选预设，右侧看结构详情。">
          <div style={{ display: "grid", gap: 8 }}>
            {activeItems.length === 0 ? (
              <div style={{ ...cardStyle, padding: 12, fontSize: 12, color: "#94a3b8" }}>当前分类暂无预设。</div>
            ) : (
              activeItems.map((item) => (
                <div
                  key={item.code}
                  style={{
                    ...cardStyle,
                    padding: 12,
                    background: item.code === selectedItem?.code ? "rgba(79,70,229,.08)" : cardStyle.background,
                    cursor: "pointer",
                  }}
                  onClick={() => setSelectedCode(item.code)}
                >
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{item.name}</div>
                  <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>{item.summary || item.code}</div>
                </div>
              ))
            )}
          </div>
        </Section>

        <Section title="预设详情" hint={selectedItem ? `${selectedItem.name} / ${selectedItem.code}` : "点击左侧预设查看详情"}>
          {!selectedItem ? (
            <div style={{ color: "#94a3b8", fontSize: 13 }}>当前没有选中的预设。</div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{selectedItem.name}</div>
                <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                  编码：{selectedItem.code} {selectedItem.summary ? ` / ${selectedItem.summary}` : ""}
                </div>
              </div>
              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>结构预览</div>
                <Preview value={selectedItem} />
              </div>
            </div>
          )}
        </Section>
      </div>
    </DashboardShell>
  );
}
