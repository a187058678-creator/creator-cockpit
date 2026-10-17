"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  DashboardShell,
  Section,
  buttonStyle,
  cardStyle,
  clearStoredPublishDraft,
  getStoredPublishDraft,
  inputStyle,
  secondaryButtonStyle,
} from "./dashboard-ui";

function copyText(value, setMessage, successText) {
  if (!value) {
    setMessage("当前没有可复制内容");
    return;
  }
  navigator.clipboard
    .writeText(value)
    .then(() => {
      setMessage(successText || "已复制");
    })
    .catch((error) => {
      setMessage(error.message || "复制失败");
    });
}

export default function PublishPageClient() {
  const [message, setMessage] = useState("正在读取发布草稿...");
  const [draft, setDraft] = useState(null);
  const [form, setForm] = useState({
    title: "",
    hook: "",
    caption: "",
    hashtags: "",
    optimizedPrompt: "",
    videoPrompt: "",
    videoUrl: "",
  });

  useEffect(() => {
    const nextDraft = getStoredPublishDraft();
    if (!nextDraft) {
      setMessage("当前还没有 AI 文案草稿");
      return;
    }
    setDraft(nextDraft);
    setForm({
      title: nextDraft.publish?.title || "",
      hook: nextDraft.publish?.hook || "",
      caption: nextDraft.publish?.caption || "",
      hashtags: nextDraft.publish?.hashtags || "",
      optimizedPrompt: nextDraft.optimized_prompt || "",
      videoPrompt: nextDraft.video_prompt || "",
      videoUrl: nextDraft.video_url || "",
    });
    setMessage(`已载入任务 #${nextDraft.task_id} 的发布草稿`);
  }, []);

  const combinedPublishCopy = useMemo(() => {
    return [form.title, form.hook, form.caption, form.hashtags]
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join("\n");
  }, [form]);

  function clearDraft() {
    clearStoredPublishDraft();
    setDraft(null);
    setForm({
      title: "",
      hook: "",
      caption: "",
      hashtags: "",
      optimizedPrompt: "",
      videoPrompt: "",
      videoUrl: "",
    });
    setMessage("发布中心草稿已清空");
  }

  return (
    <DashboardShell
      title="发布中心"
      description="这里先承接 AI 文案工作流送过来的草稿，方便继续复制、整理和后续接正式发布链。"
      action={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <Link href="/agent-flow" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
            返回 AI 文案工作流
          </Link>
          <button type="button" style={secondaryButtonStyle} onClick={clearDraft}>
            清空草稿
          </button>
        </div>
      }
    >
      <Section title="当前消息" hint="显示最近一次接收或复制动作。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
        }}
      >
        <Section title="草稿来源" hint="记录这份文案是从哪条 AI 任务过来的。">
          {draft ? (
            <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
              <div>任务 ID：#{draft.task_id}</div>
              <div>任务标题：{draft.task_title || "-"}</div>
              <div>账号组：{draft.group_id || "-"}</div>
              <div>选题：{draft.selected_topic || "-"}</div>
              <div>来源说明：{draft.source_value || "-"}</div>
            </div>
          ) : (
            <div style={{ fontSize: 13, color: "#94a3b8" }}>还没有收到 AI 文案页推送过来的草稿。</div>
          )}
        </Section>

        <Section title="快捷复制" hint="常用内容单独复制，减少手动整理。">
          <div style={{ display: "grid", gap: 8 }}>
            <button type="button" style={buttonStyle} onClick={() => copyText(combinedPublishCopy, setMessage, "已复制完整发布文案")}>
              复制完整发布文案
            </button>
            <button type="button" style={secondaryButtonStyle} onClick={() => copyText(form.title, setMessage, "已复制标题")}>
              复制标题
            </button>
            <button type="button" style={secondaryButtonStyle} onClick={() => copyText(form.caption, setMessage, "已复制正文")}>
              复制正文
            </button>
            <button type="button" style={secondaryButtonStyle} onClick={() => copyText(form.optimizedPrompt, setMessage, "已复制优化提示词")}>
              复制优化提示词
            </button>
          </div>
        </Section>
      </section>

      <Section title="发布草稿" hint="可以在这里继续微调，再复制到你的正式发布链。">
        <div style={{ display: "grid", gap: 12 }}>
          <input
            style={inputStyle}
            value={form.title}
            onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
            placeholder="标题"
          />
          <textarea
            style={{ ...inputStyle, minHeight: 72, resize: "vertical" }}
            value={form.hook}
            onChange={(event) => setForm((prev) => ({ ...prev, hook: event.target.value }))}
            placeholder="Hook"
          />
          <textarea
            style={{ ...inputStyle, minHeight: 140, resize: "vertical" }}
            value={form.caption}
            onChange={(event) => setForm((prev) => ({ ...prev, caption: event.target.value }))}
            placeholder="正文"
          />
          <input
            style={inputStyle}
            value={form.hashtags}
            onChange={(event) => setForm((prev) => ({ ...prev, hashtags: event.target.value }))}
            placeholder="标签"
          />
        </div>
      </Section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
        }}
      >
        <Section title="提示词" hint="保留 AI 生成时的核心提示词，方便继续投喂视频模型。">
          <div style={{ display: "grid", gap: 12 }}>
            <textarea
              style={{ ...inputStyle, minHeight: 180, resize: "vertical" }}
              value={form.optimizedPrompt}
              onChange={(event) => setForm((prev) => ({ ...prev, optimizedPrompt: event.target.value }))}
              placeholder="优化提示词"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 180, resize: "vertical" }}
              value={form.videoPrompt}
              onChange={(event) => setForm((prev) => ({ ...prev, videoPrompt: event.target.value }))}
              placeholder="视频提示词"
            />
          </div>
        </Section>

        <Section title="视频结果" hint="如果 AI 工作流已经拿到了视频地址，这里会直接带过来。">
          <div style={{ ...cardStyle, padding: 14, display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
            <div style={{ wordBreak: "break-all" }}>{form.videoUrl || "当前还没有视频结果 URL"}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {form.videoUrl ? (
                <a
                  href={form.videoUrl}
                  target="_blank"
                  rel="noreferrer"
                  style={{ ...buttonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                >
                  打开视频
                </a>
              ) : null}
              <button
                type="button"
                style={secondaryButtonStyle}
                onClick={() => copyText(form.videoUrl, setMessage, "已复制视频地址")}
              >
                复制视频地址
              </button>
            </div>
          </div>
        </Section>
      </section>
    </DashboardShell>
  );
}
