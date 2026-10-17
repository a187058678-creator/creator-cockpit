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
  const [providers, setProviders] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [groupFilter, setGroupFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");

  async function loadGroups() {
    const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
    setGroups(data.items || []);
  }

  async function loadProviders() {
    const data = await readJson(await authFetch("/api/oauth/providers", { cache: "no-store" }));
    setProviders(data.items || []);
  }

  async function loadAccounts(nextGroupId = groupFilter, nextPlatform = platformFilter) {
    const query = new URLSearchParams();
    if (nextGroupId) {
      query.set("group_id", nextGroupId);
    }
    if (nextPlatform) {
      query.set("platform", nextPlatform);
    }
    query.set("limit", "100");
    const data = await readJson(await authFetch(`/api/platform-accounts?${query.toString()}`, { cache: "no-store" }));
    setAccounts(data.items || []);
  }

  async function loadSessions(nextGroupId = groupFilter, nextPlatform = platformFilter) {
    const query = new URLSearchParams();
    if (nextGroupId) {
      query.set("group_id", nextGroupId);
    }
    if (nextPlatform) {
      query.set("platform", nextPlatform);
    }
    query.set("limit", "20");
    const data = await readJson(await authFetch(`/api/oauth-sessions?${query.toString()}`, { cache: "no-store" }));
    setSessions(data.items || []);
  }

  async function reloadAll(nextGroupId = groupFilter, nextPlatform = platformFilter) {
    setMessage("正在刷新平台账号...");
    try {
      await Promise.all([loadGroups(), loadProviders(), loadAccounts(nextGroupId, nextPlatform), loadSessions(nextGroupId, nextPlatform)]);
      setMessage("平台账号已刷新");
    } catch (error) {
      setMessage(error.message || "刷新平台账号失败");
    }
  }

  useEffect(() => {
    reloadAll("", "");
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const oauthStatus = params.get("oauth_status") || "";
    const oauthPlatform = params.get("oauth_platform") || "";
    const oauthMessage = params.get("oauth_message") || "";
    if (!oauthStatus) {
      return;
    }
    setMessage(`${platformLabels[oauthPlatform] || oauthPlatform || "OAuth"}：${oauthMessage || oauthStatus}`);
    reloadAll(groupFilter, platformFilter);
  }, []);

  const summaryCards = useMemo(() => {
    const enabledProviders = providers.filter((item) => item.enabled).length;
    const activeAccounts = accounts.filter((item) => item.status === "active").length;
    return [
      { label: "已配置平台", value: String(enabledProviders), hint: "可发起 OAuth", ok: enabledProviders > 0 },
      { label: "已接入账号", value: String(accounts.length), hint: "当前筛选下的平台账号", ok: accounts.length > 0 },
      { label: "有效账号", value: String(activeAccounts), hint: "状态 active", ok: activeAccounts > 0 },
      { label: "最近连接会话", value: String(sessions.length), hint: "最近 20 条 OAuth 会话", ok: sessions.length > 0 },
    ];
  }, [providers, accounts, sessions]);

  async function startOauth(platform) {
    setBusy(`connect-${platform}`);
    setMessage(`正在发起 ${platformLabels[platform] || platform} OAuth...`);
    try {
      const query = groupFilter ? `?group_id=${encodeURIComponent(groupFilter)}` : "";
      const data = await readJson(await authFetch(`/api/oauth/${platform}/start${query}`, { cache: "no-store" }));
      if (!data.auth_url) {
        throw new Error("后端没有返回授权地址");
      }
      window.location.href = data.auth_url;
    } catch (error) {
      setMessage(error.message || "发起 OAuth 失败");
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
          body: JSON.stringify({ status: nextStatus }),
        })
      );
      setMessage(`账号 #${account.id} 已更新为 ${nextStatus}`);
      await reloadAll(groupFilter, platformFilter);
    } catch (error) {
      setMessage(error.message || "更新平台账号失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <DashboardShell
      title="平台账号"
      description="这里集中处理 TikTok、YouTube、Facebook、Instagram、X 的 OAuth 绑定和账号归组。"
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
            <option value="">全部账号组</option>
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
          <button type="button" style={buttonStyle} onClick={() => reloadAll(groupFilter, platformFilter)}>
            刷新页面
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

      <Section title="当前消息" hint="最近一次 OAuth 发起、回调或状态更新结果。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>

      <Section title="OAuth 接入平台" hint="先配好每个平台的 client_id / secret，再按组发起绑定。">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 12,
          }}
        >
          {providers.map((provider) => (
            <div
              key={provider.code}
              style={{
                border: "1px solid #26314f",
                borderRadius: 14,
                padding: 14,
                background: "#0f172a",
                display: "grid",
                gap: 10,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ fontSize: 16, fontWeight: 700 }}>{provider.label}</div>
                <div style={{ fontSize: 12, color: provider.enabled ? "#86efac" : "#fca5a5" }}>
                  {provider.enabled ? "已配置" : "待配置"}
                </div>
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
                Scopes: {(provider.scopes || []).join(", ") || "-"}
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                {provider.pkce_required ? "需要 PKCE" : "标准 OAuth 2.0"}
              </div>
              <button
                type="button"
                style={provider.enabled ? buttonStyle : secondaryButtonStyle}
                disabled={!provider.enabled || busy === `connect-${provider.code}`}
                onClick={() => startOauth(provider.code)}
              >
                {busy === `connect-${provider.code}` ? "跳转中..." : `绑定 ${provider.label}`}
              </button>
            </div>
          ))}
        </div>
      </Section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.2fr) minmax(380px, .8fr)",
          gap: 16,
        }}
      >
        <Section title="已接入账号" hint="这里看平台账号归属、令牌状态和最近同步时间。">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>平台</th>
                  <th style={tableHeadStyle}>账号</th>
                  <th style={tableHeadStyle}>账号组</th>
                  <th style={tableHeadStyle}>状态</th>
                  <th style={tableHeadStyle}>令牌过期</th>
                  <th style={tableHeadStyle}>操作</th>
                </tr>
              </thead>
              <tbody>
                {accounts.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      当前筛选条件下还没有平台账号。
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
                      <td style={tableCellStyle}>{groups.find((group) => group.id === item.group_id)?.group_name || "-"}</td>
                      <td style={tableCellStyle}>{item.status}</td>
                      <td style={tableCellStyle}>
                        <div>{formatDate(item.token_expires_at)}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          最近同步 {formatDate(item.last_synced_at)}
                        </div>
                      </td>
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

        <Section title="最近 OAuth 会话" hint="看最近发起、完成、失败的连接尝试。">
          <div style={{ overflowX: "auto", maxHeight: 480 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>平台</th>
                  <th style={tableHeadStyle}>状态</th>
                  <th style={tableHeadStyle}>账号组</th>
                  <th style={tableHeadStyle}>时间</th>
                </tr>
              </thead>
              <tbody>
                {sessions.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      还没有 OAuth 会话。
                    </td>
                  </tr>
                ) : (
                  sessions.map((item) => (
                    <tr key={item.id}>
                      <td style={tableCellStyle}>
                        <div>{platformLabels[item.platform] || item.platform}</div>
                        {item.error_message ? (
                          <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>{item.error_message}</div>
                        ) : null}
                      </td>
                      <td style={tableCellStyle}>{item.status}</td>
                      <td style={tableCellStyle}>{groups.find((group) => group.id === item.group_id)?.group_name || "-"}</td>
                      <td style={tableCellStyle}>{formatDate(item.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>
      </section>
    </DashboardShell>
  );
}
