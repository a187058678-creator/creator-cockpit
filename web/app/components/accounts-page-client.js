"use client";

import { useEffect, useMemo, useState } from "react";
import {
  DashboardShell,
  Section,
  SummaryCard,
  authFetch,
  buttonStyle,
  formatDate,
  inputStyle,
  readJson,
  secondaryButtonStyle,
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

const platformLabels = {
  tiktok: "TikTok",
  youtube: "YouTube",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
};

export default function AccountsPageClient() {
  const [groups, setGroups] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [groupFilter, setGroupFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("先选择账号组并保存组级 Post for Me API Key，再开始绑定远程账号。");

  const currentGroup = useMemo(
    () => groups.find((item) => String(item.id) === String(groupFilter)) || null,
    [groups, groupFilter]
  );
  const canManageGroupApiKey = currentUser?.role === "admin";

  async function loadGroups() {
    const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
    return data.items || [];
  }

  async function loadCurrentUser() {
    const data = await readJson(await authFetch("/api/auth/me", { cache: "no-store" }));
    setCurrentUser(data.item?.user || null);
  }

  async function loadAccounts(nextGroupId = groupFilter, nextPlatform = platformFilter) {
    const query = new URLSearchParams();
    query.set("auth_type", "postforme");
    query.set("limit", "100");
    if (nextGroupId) {
      query.set("group_id", nextGroupId);
    }
    if (nextPlatform) {
      query.set("platform", nextPlatform);
    }
    const data = await readJson(await authFetch(`/api/platform-accounts?${query.toString()}`, { cache: "no-store" }));
    setAccounts(data.items || []);
  }

  async function reloadAll(nextGroupId = groupFilter, nextPlatform = platformFilter) {
    setMessage("正在刷新 Post for Me 账号...");
    try {
      const [nextGroups] = await Promise.all([loadGroups(), loadCurrentUser()]);
      setGroups(nextGroups);
      let effectiveGroupId = nextGroupId;
      if (!effectiveGroupId && nextGroups.length === 1) {
        effectiveGroupId = String(nextGroups[0].id);
        setGroupFilter(effectiveGroupId);
      }
      await loadAccounts(effectiveGroupId, nextPlatform);
      setMessage("Post for Me 账号已刷新");
    } catch (error) {
      setMessage(error.message || "刷新平台账号失败");
    }
  }

  useEffect(() => {
    reloadAll("", "");
  }, []);

  useEffect(() => {
    setApiKeyInput("");
  }, [groupFilter]);

  const summaryCards = useMemo(() => {
    const activeAccounts = accounts.filter((item) => item.status === "active").length;
    const groupedAccounts = accounts.filter((item) => item.group_id).length;
    const connectedPlatforms = new Set(accounts.map((item) => item.platform).filter(Boolean));
    return [
      { label: "已接入账号", value: String(accounts.length), hint: "来自 Post for Me 同步", ok: accounts.length > 0 },
      { label: "有效账号", value: String(activeAccounts), hint: "状态 active", ok: activeAccounts > 0 },
      { label: "已归组账号", value: String(groupedAccounts), hint: "已经挂到账号组", ok: groupedAccounts > 0 },
      { label: "覆盖平台", value: String(connectedPlatforms.size), hint: "当前已同步的平台数", ok: connectedPlatforms.size > 0 },
    ];
  }, [accounts]);

  async function saveGroupApiKey(nextValue) {
    if (!canManageGroupApiKey) {
      setMessage("只有管理员可以修改组级 Post for Me API Key");
      return;
    }
    if (!groupFilter) {
      setMessage("请先选择账号组");
      return;
    }
    setBusy("save-group-key");
    setMessage("正在保存组级 Post for Me API Key...");
    try {
      await readJson(
        await authFetch(`/api/groups/${groupFilter}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postforme_api_key: nextValue }),
        })
      );
      await reloadAll(groupFilter, platformFilter);
      setApiKeyInput("");
      setMessage(nextValue ? "组级 Post for Me API Key 已保存" : "组级 Post for Me API Key 已清空");
    } catch (error) {
      setMessage(error.message || "保存组级 API Key 失败");
    } finally {
      setBusy("");
    }
  }

  async function syncAccounts() {
    if (!groupFilter) {
      setMessage("请先选择账号组");
      return;
    }
    setBusy("sync");
    setMessage("正在从 Post for Me 同步远程账号...");
    try {
      await readJson(
        await authFetch("/api/postforme/social-accounts/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            group_id: Number(groupFilter),
            platforms: platformFilter ? [platformFilter] : [],
          }),
        })
      );
      await reloadAll(groupFilter, platformFilter);
      setMessage("远程账号已同步到平台账号页");
    } catch (error) {
      setMessage(error.message || "同步远程账号失败");
    } finally {
      setBusy("");
    }
  }

  async function startConnect(platform) {
    if (!groupFilter) {
      setMessage("请先选择账号组");
      return;
    }
    setBusy(`connect-${platform}`);
    setMessage(`正在为 ${platformLabels[platform] || platform} 生成授权地址...`);
    try {
      const data = await readJson(
        await authFetch("/api/postforme/social-accounts/auth-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform,
            group_id: Number(groupFilter),
          }),
        })
      );
      if (!data.auth_url) {
        throw new Error("Post for Me 没有返回授权地址");
      }
      window.open(data.auth_url, "_blank", "noopener,noreferrer");
      setMessage(`已打开 ${platformLabels[platform] || platform} 授权页，完成后回到这里点击“同步远程账号”`);
    } catch (error) {
      setMessage(error.message || "创建授权地址失败");
    } finally {
      setBusy("");
    }
  }

  async function updateAccountStatus(account, nextStatus) {
    setBusy(`account-${account.id}`);
    setMessage(`正在更新账号 #${account.id}...`);
    try {
      await readJson(
        await authFetch(`/api/platform-accounts/${account.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            group_id: account.group_id,
            status: nextStatus,
          }),
        })
      );
      await reloadAll(groupFilter, platformFilter);
      setMessage(`账号 #${account.id} 已更新为 ${nextStatus}`);
    } catch (error) {
      setMessage(error.message || "更新账号状态失败");
    } finally {
      setBusy("");
    }
  }

  async function updateAccountGroup(account, nextGroupId) {
    setBusy(`account-group-${account.id}`);
    setMessage(`正在更新账号 #${account.id} 的归组...`);
    try {
      await readJson(
        await authFetch(`/api/platform-accounts/${account.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            group_id: nextGroupId ? Number(nextGroupId) : null,
            status: account.status,
          }),
        })
      );
      await reloadAll(groupFilter, platformFilter);
      setMessage(`账号 #${account.id} 的归组已更新`);
    } catch (error) {
      setMessage(error.message || "更新账号归组失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <DashboardShell
      title="平台账号"
      description="这里按账号组保存 Post for Me API Key，团队成员选中同一个组后就能共用绑定和发帖能力。"
      action={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <select
            style={{ ...inputStyle, width: 180 }}
            value={groupFilter}
            onChange={(event) => {
              const nextValue = event.target.value;
              setGroupFilter(nextValue);
              reloadAll(nextValue, platformFilter);
            }}
          >
            <option value="">选择账号组</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.group_name}
              </option>
            ))}
          </select>
          <select
            style={{ ...inputStyle, width: 150 }}
            value={platformFilter}
            onChange={(event) => {
              const nextValue = event.target.value;
              setPlatformFilter(nextValue);
              reloadAll(groupFilter, nextValue);
            }}
          >
            <option value="">全部平台</option>
            {Object.entries(platformLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button type="button" style={secondaryButtonStyle} onClick={syncAccounts} disabled={busy === "sync"}>
            {busy === "sync" ? "同步中..." : "同步远程账号"}
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
          <SummaryCard key={item.label} label={item.label} value={item.value} hint={item.hint} ok={item.ok} />
        ))}
      </section>

      <Section title="当前消息" hint="最近一次组级配置保存、授权发起、同步或状态更新结果。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>

      <Section title="组级 Post for Me API Key" hint="API Key 保存到后端账号组配置里，团队成员不需要各自再填一次。">
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ fontSize: 13, color: "#94a3b8" }}>
            当前账号组：{currentGroup?.group_name || "未选择"}{currentGroup?.has_postforme_api_key ? ` | 已配置 ${currentGroup.masked_postforme_api_key || ""}` : " | 未配置"}
          </div>
          <div style={{ fontSize: 13, color: canManageGroupApiKey ? "#94a3b8" : "#fbbf24" }}>
            当前角色：{currentUser?.role || "未登录"}{canManageGroupApiKey ? "，可修改当前组 API Key" : "，当前区块只读，仅管理员可修改"}
          </div>
          <input
            style={inputStyle}
            value={apiKeyInput}
            onChange={(event) => setApiKeyInput(event.target.value)}
            placeholder="输入新的 Post for Me API Key；留空可点击清空"
            disabled={!canManageGroupApiKey}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={buttonStyle}
              onClick={() => saveGroupApiKey(apiKeyInput)}
              disabled={busy === "save-group-key" || !canManageGroupApiKey}
            >
              {busy === "save-group-key" ? "保存中..." : "保存到当前组"}
            </button>
            <button
              type="button"
              style={secondaryButtonStyle}
              onClick={() => saveGroupApiKey("")}
              disabled={busy === "save-group-key" || !currentGroup?.has_postforme_api_key || !canManageGroupApiKey}
            >
              清空当前组 API Key
            </button>
          </div>
        </div>
      </Section>

      <Section title="绑定远程账号" hint="点平台按钮会打开 Post for Me 授权页；授权完成后回到这里，再点“同步远程账号”。">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 12,
          }}
        >
          {Object.entries(platformLabels).map(([platform, label]) => (
            <div
              key={platform}
              style={{
                border: "1px solid #26314f",
                borderRadius: 14,
                padding: 14,
                background: "#0f172a",
                display: "grid",
                gap: 10,
              }}
            >
              <div style={{ fontSize: 16, fontWeight: 700 }}>{label}</div>
              <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
                绑定会使用当前账号组保存的 Post for Me API Key。
              </div>
              <button
                type="button"
                style={buttonStyle}
                disabled={busy === `connect-${platform}` || !currentGroup?.has_postforme_api_key}
                onClick={() => startConnect(platform)}
              >
                {busy === `connect-${platform}` ? "打开中..." : `绑定 ${label}`}
              </button>
            </div>
          ))}
        </div>
      </Section>

      <Section title="已同步账号" hint="这里显示已经从 Post for Me 同步回来的账号，你可以继续做归组和停用。">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={tableHeadStyle}>平台</th>
                <th style={tableHeadStyle}>账号</th>
                <th style={tableHeadStyle}>账号组</th>
                <th style={tableHeadStyle}>状态</th>
                <th style={tableHeadStyle}>最近同步</th>
                <th style={tableHeadStyle}>操作</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                    当前还没有同步到 Post for Me 账号。
                  </td>
                </tr>
              ) : (
                accounts.map((item) => (
                  <tr key={item.id}>
                    <td style={tableCellStyle}>{platformLabels[item.platform] || item.platform}</td>
                    <td style={tableCellStyle}>
                      <div>{item.account_name || "-"}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                        {item.account_handle || item.platform_user_id}
                      </div>
                    </td>
                    <td style={tableCellStyle}>
                      <select
                        style={{ ...inputStyle, minWidth: 140 }}
                        value={item.group_id || ""}
                        onChange={(event) => updateAccountGroup(item, event.target.value)}
                        disabled={busy === `account-group-${item.id}`}
                      >
                        <option value="">未分组</option>
                        {groups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.group_name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={tableCellStyle}>{item.status}</td>
                    <td style={tableCellStyle}>{formatDate(item.last_synced_at)}</td>
                    <td style={tableCellStyle}>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button
                          type="button"
                          style={secondaryButtonStyle}
                          disabled={busy === `account-${item.id}` || item.status === "active"}
                          onClick={() => updateAccountStatus(item, "active")}
                        >
                          启用
                        </button>
                        <button
                          type="button"
                          style={secondaryButtonStyle}
                          disabled={busy === `account-${item.id}` || item.status === "disabled"}
                          onClick={() => updateAccountStatus(item, "disabled")}
                        >
                          停用
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
