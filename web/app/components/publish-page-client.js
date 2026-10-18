"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  DashboardShell,
  Section,
  authFetch,
  buttonStyle,
  cardStyle,
  clearStoredPublishDraft,
  getStoredPublishDraft,
  inputStyle,
  readJson,
  secondaryButtonStyle,
} from "./dashboard-ui";

const platformLabels = {
  tiktok: "TikTok",
  youtube: "YouTube",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
};

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
  const [groups, setGroups] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountIds, setSelectedAccountIds] = useState([]);
  const [busy, setBusy] = useState("");
  const [publishForm, setPublishForm] = useState({
    title: "",
    hook: "",
    caption: "",
    hashtags: "",
    optimizedPrompt: "",
    videoPrompt: "",
    videoUrl: "",
    scheduledAt: "",
  });

  const currentGroup = useMemo(
    () => groups.find((item) => String(item.id) === String(draft?.group_id || "")) || null,
    [groups, draft?.group_id]
  );

  useEffect(() => {
    const nextDraft = getStoredPublishDraft();
    if (!nextDraft) {
      setMessage("当前还没有 AI 文案草稿");
      return;
    }
    setDraft(nextDraft);
    setPublishForm({
      title: nextDraft.publish?.title || "",
      hook: nextDraft.publish?.hook || "",
      caption: nextDraft.publish?.caption || "",
      hashtags: nextDraft.publish?.hashtags || "",
      optimizedPrompt: nextDraft.optimized_prompt || "",
      videoPrompt: nextDraft.video_prompt || "",
      videoUrl: nextDraft.video_url || "",
      scheduledAt: "",
    });
    setMessage(`已载入任务 #${nextDraft.task_id} 的发布草稿`);
  }, []);

  useEffect(() => {
    authFetch("/api/groups", { cache: "no-store" })
      .then(readJson)
      .then((data) => {
        setGroups(data.items || []);
      })
      .catch((error) => {
        setMessage(error.message || "加载账号组失败");
      });
  }, []);

  const combinedPublishCopy = useMemo(() => {
    return [publishForm.title, publishForm.hook, publishForm.caption, publishForm.hashtags]
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join("\n");
  }, [publishForm]);

  async function loadAccounts() {
    if (!draft?.group_id) {
      setAccounts([]);
      return;
    }
    const query = new URLSearchParams();
    query.set("auth_type", "postforme");
    query.set("status", "active");
    query.set("limit", "100");
    query.set("group_id", String(draft.group_id));
    const data = await readJson(await authFetch(`/api/platform-accounts?${query.toString()}`, { cache: "no-store" }));
    setAccounts(data.items || []);
  }

  async function syncAccounts() {
    if (!draft?.group_id) {
      setMessage("当前草稿还没有关联账号组");
      return;
    }
    setBusy("sync");
    setMessage("正在同步 Post for Me 账号...");
    try {
      await readJson(
        await authFetch("/api/postforme/social-accounts/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            group_id: draft.group_id,
            platforms: [],
          }),
        })
      );
      await loadAccounts();
      setMessage("Post for Me 账号已同步");
    } catch (error) {
      setMessage(error.message || "同步发布账号失败");
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    loadAccounts().catch((error) => {
      setMessage(error.message || "加载发布账号失败");
    });
  }, [draft?.group_id]);

  function clearDraft() {
    clearStoredPublishDraft();
    setDraft(null);
    setSelectedAccountIds([]);
    setPublishForm({
      title: "",
      hook: "",
      caption: "",
      hashtags: "",
      optimizedPrompt: "",
      videoPrompt: "",
      videoUrl: "",
      scheduledAt: "",
    });
    setMessage("发布中心草稿已清空");
  }

  function toggleAccount(accountId) {
    setSelectedAccountIds((prev) =>
      prev.includes(accountId) ? prev.filter((item) => item !== accountId) : [...prev, accountId]
    );
  }

  async function createSocialPost() {
    if (!draft?.group_id) {
      setMessage("当前草稿还没有关联账号组");
      return;
    }
    if (selectedAccountIds.length === 0) {
      setMessage("请先选择至少一个发布账号");
      return;
    }
    setBusy("publish");
    setMessage("正在通过 Post for Me 创建发布任务...");
    try {
      const scheduledAt = publishForm.scheduledAt ? new Date(publishForm.scheduledAt).toISOString() : null;
      const data = await readJson(
        await authFetch("/api/postforme/social-posts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            group_id: draft.group_id,
            social_account_ids: selectedAccountIds,
            caption: combinedPublishCopy,
            media_urls: publishForm.videoUrl ? [publishForm.videoUrl] : [],
            scheduled_at: scheduledAt,
          }),
        })
      );
      const postId = data.item?.id || data.item?.data?.id || "";
      setMessage(postId ? `Post for Me 发布任务已创建：${postId}` : "Post for Me 发布任务已创建");
    } catch (error) {
      setMessage(error.message || "创建发布任务失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <DashboardShell
      title="发布中心"
      description="这里直接使用系统内置的 Post for Me 连接能力，不需要再单独配置 API Key。"
      action={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <Link href="/agent-flow" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
            返回 AI 文案工作流
          </Link>
          <Link href="/accounts" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
            去平台账号页
          </Link>
          <button type="button" style={secondaryButtonStyle} onClick={clearDraft}>
            清空草稿
          </button>
        </div>
      }
    >
      <Section title="当前消息" hint="显示最近一次接收、复制、同步或发帖动作。">
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
              <div>账号组：{currentGroup?.group_name || draft.group_id || "-"}</div>
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
            <button type="button" style={secondaryButtonStyle} onClick={() => copyText(publishForm.title, setMessage, "已复制标题")}>
              复制标题
            </button>
            <button type="button" style={secondaryButtonStyle} onClick={() => copyText(publishForm.caption, setMessage, "已复制正文")}>
              复制正文
            </button>
            <button type="button" style={secondaryButtonStyle} onClick={() => copyText(publishForm.optimizedPrompt, setMessage, "已复制优化提示词")}>
              复制优化提示词
            </button>
          </div>
        </Section>
      </section>

      <Section title="发布账号同步" hint="当前会直接使用系统内置的 Post for Me 连接配置同步本组可用账号。">
        <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
          <div>当前账号组：{currentGroup?.group_name || "未匹配到账号组"}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={syncAccounts}
              disabled={busy === "sync" || !draft?.group_id}
            >
              {busy === "sync" ? "同步中..." : "同步发布账号"}
            </button>
          </div>
        </div>
      </Section>

      <Section title="发布账号" hint="这里列出当前组下已同步的 Post for Me active 账号。">
        <div style={{ display: "grid", gap: 10 }}>
          {accounts.length === 0 ? (
            <div style={{ fontSize: 13, color: "#94a3b8" }}>当前还没有可用的 Post for Me 账号，先去平台账号页绑定并同步。</div>
          ) : (
            accounts.map((account) => (
              <label
                key={account.id}
                style={{
                  ...cardStyle,
                  padding: 12,
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedAccountIds.includes(account.platform_user_id)}
                  onChange={() => toggleAccount(account.platform_user_id)}
                  style={{ marginTop: 4 }}
                />
                <div style={{ display: "grid", gap: 4 }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>
                    {platformLabels[account.platform] || account.platform} / {account.account_name || account.platform_user_id}
                  </div>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>
                    {account.account_handle || account.platform_user_id} | 组 {account.group_id || "-"} | {account.status}
                  </div>
                </div>
              </label>
            ))
          )}
        </div>
      </Section>

      <Section title="发布草稿" hint="可以在这里继续微调，再直接提交到 Post for Me。">
        <div style={{ display: "grid", gap: 12 }}>
          <input
            style={inputStyle}
            value={publishForm.title}
            onChange={(event) => setPublishForm((prev) => ({ ...prev, title: event.target.value }))}
            placeholder="标题"
          />
          <textarea
            style={{ ...inputStyle, minHeight: 72, resize: "vertical" }}
            value={publishForm.hook}
            onChange={(event) => setPublishForm((prev) => ({ ...prev, hook: event.target.value }))}
            placeholder="Hook"
          />
          <textarea
            style={{ ...inputStyle, minHeight: 140, resize: "vertical" }}
            value={publishForm.caption}
            onChange={(event) => setPublishForm((prev) => ({ ...prev, caption: event.target.value }))}
            placeholder="正文"
          />
          <input
            style={inputStyle}
            value={publishForm.hashtags}
            onChange={(event) => setPublishForm((prev) => ({ ...prev, hashtags: event.target.value }))}
            placeholder="标签"
          />
          <input
            style={inputStyle}
            type="datetime-local"
            value={publishForm.scheduledAt}
            onChange={(event) => setPublishForm((prev) => ({ ...prev, scheduledAt: event.target.value }))}
          />
          <div style={{ fontSize: 12, color: "#94a3b8" }}>
            留空就是立即发布；填写时间就是定时发布。
          </div>
          <button
            type="button"
            style={buttonStyle}
            onClick={createSocialPost}
            disabled={busy === "publish" || !draft?.group_id}
          >
            {busy === "publish" ? "提交中..." : "提交到 Post for Me"}
          </button>
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
              value={publishForm.optimizedPrompt}
              onChange={(event) => setPublishForm((prev) => ({ ...prev, optimizedPrompt: event.target.value }))}
              placeholder="优化提示词"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 180, resize: "vertical" }}
              value={publishForm.videoPrompt}
              onChange={(event) => setPublishForm((prev) => ({ ...prev, videoPrompt: event.target.value }))}
              placeholder="视频提示词"
            />
          </div>
        </Section>

        <Section title="视频结果" hint="如果 AI 工作流已经拿到了视频地址，这里会直接带过来给 Post for Me 当媒体 URL。">
          <div style={{ ...cardStyle, padding: 14, display: "grid", gap: 10, fontSize: 13, color: "#cbd5e1" }}>
            <input
              style={inputStyle}
              value={publishForm.videoUrl}
              onChange={(event) => setPublishForm((prev) => ({ ...prev, videoUrl: event.target.value }))}
              placeholder="视频 URL"
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {publishForm.videoUrl ? (
                <a
                  href={publishForm.videoUrl}
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
                onClick={() => copyText(publishForm.videoUrl, setMessage, "已复制视频地址")}
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
