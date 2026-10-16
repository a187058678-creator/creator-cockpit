"use client";

import { useEffect, useMemo, useState } from "react";
import {
  DashboardShell,
  Section,
  SummaryCard,
  authFetch,
  authStorageKey,
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

export default function AccessPageClient() {
  const [users, setUsers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [workerTokens, setWorkerTokens] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [taskExecutions, setTaskExecutions] = useState([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [groupMembers, setGroupMembers] = useState([]);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [accessToken, setAccessToken] = useState("");
  const [sessionInfo, setSessionInfo] = useState(null);
  const [loginForm, setLoginForm] = useState({
    username: "",
    password: "",
  });
  const [userForm, setUserForm] = useState({
    username: "",
    password: "",
    display_name: "",
    role: "admin",
    status: "active",
  });
  const [groupForm, setGroupForm] = useState({
    group_name: "",
    group_code: "",
    owner_user_id: "",
    status: "active",
    remark: "",
  });
  const [memberForm, setMemberForm] = useState({
    user_id: "",
    member_role: "editor",
  });
  const [workerTokenForm, setWorkerTokenForm] = useState({
    worker_code: "worker-cn-001",
    token_name: "深圳一号机 Token",
    group_id: "",
    issued_by_user_id: "",
    expire_days: 30,
  });
  const [lastIssuedToken, setLastIssuedToken] = useState("");

  const userOptions = useMemo(
    () => users.map((item) => ({ label: `${item.display_name} (${item.username})`, value: String(item.id) })),
    [users]
  );

  async function loadUsers() {
    const data = await readJson(await authFetch("/api/users", { cache: "no-store" }));
    setUsers(data.items || []);
  }

  async function loadGroups() {
    const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
    const items = data.items || [];
    setGroups(items);
    if (!selectedGroupId && items[0]) {
      setSelectedGroupId(String(items[0].id));
    }
  }

  async function loadWorkerTokens(groupId = selectedGroupId) {
    const data = await readJson(
      await authFetch(`/api/worker-tokens?group_id=${encodeURIComponent(groupId)}`, { cache: "no-store" })
    );
    setWorkerTokens(data.items || []);
  }

  async function loadAuditLogs() {
    const data = await readJson(await authFetch("/api/audit-logs", { cache: "no-store" }));
    setAuditLogs(data.items || []);
  }

  async function loadTaskExecutions(groupId = selectedGroupId) {
    const data = await readJson(
      await authFetch(`/api/task-executions?group_id=${encodeURIComponent(groupId)}&limit=20`, { cache: "no-store" })
    );
    setTaskExecutions(data.items || []);
  }

  async function loadGroupMembers(groupId) {
    if (!groupId) {
      setGroupMembers([]);
      return;
    }
    const data = await readJson(await authFetch(`/api/groups/${groupId}/members`, { cache: "no-store" }));
    setGroupMembers(data.items || []);
  }

  async function loadSession(token, { silent = false } = {}) {
    if (!token) {
      setSessionInfo(null);
      return;
    }
    try {
      const data = await readJson(
        await fetch("/api/auth/me", {
          cache: "no-store",
          headers: { Authorization: `Bearer ${token}` },
        })
      );
      setSessionInfo(data.item || null);
    } catch (error) {
      setSessionInfo(null);
      setAccessToken("");
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(authStorageKey);
      }
      if (!silent) {
        setMessage(error.message || "登录状态已失效");
      }
    }
  }

  async function reloadAll(nextSelectedGroupId = selectedGroupId, nextToken = accessToken) {
    if (!nextToken) {
      setUsers([]);
      setGroups([]);
      setWorkerTokens([]);
      setAuditLogs([]);
      setTaskExecutions([]);
      setGroupMembers([]);
      setSessionInfo(null);
      setMessage("请先登录；首次使用可先创建管理员账号");
      return;
    }
    setMessage("正在刷新访问控制...");
    try {
      await Promise.all([
        loadUsers(),
        loadGroups(),
        loadWorkerTokens(nextSelectedGroupId),
        loadAuditLogs(),
        loadTaskExecutions(nextSelectedGroupId),
        loadSession(nextToken, { silent: true }),
      ]);
      await loadGroupMembers(nextSelectedGroupId);
      setMessage("访问控制已刷新");
    } catch (error) {
      setMessage(error.message || "刷新访问控制失败");
    }
  }

  useEffect(() => {
    const storedToken =
      typeof window !== "undefined" ? window.localStorage.getItem(authStorageKey) || "" : "";
    if (storedToken) {
      setAccessToken(storedToken);
    }
    reloadAll("", storedToken);
  }, []);

  useEffect(() => {
    if (!accessToken || !selectedGroupId) {
      return;
    }
    Promise.all([
      loadGroupMembers(selectedGroupId),
      loadWorkerTokens(selectedGroupId),
      loadTaskExecutions(selectedGroupId),
    ]).catch((error) => {
      setMessage(error.message || "刷新当前账号组数据失败");
    });
  }, [selectedGroupId]);

  async function login(event) {
    event.preventDefault();
    setBusy("login");
    setMessage("正在登录...");
    try {
      const data = await readJson(
        await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(loginForm),
        })
      );
      const nextToken = data.item?.access_token || "";
      setAccessToken(nextToken);
      setSessionInfo(data.item || null);
      setLoginForm((prev) => ({ ...prev, password: "" }));
      if (typeof window !== "undefined") {
        window.localStorage.setItem(authStorageKey, nextToken);
      }
      setMessage(`登录成功：${data.item?.user?.display_name || data.item?.user?.username || "当前用户"}`);
      await reloadAll(selectedGroupId, nextToken);
    } catch (error) {
      setMessage(error.message || "登录失败");
    } finally {
      setBusy("");
    }
  }

  async function logout() {
    if (!accessToken) {
      setSessionInfo(null);
      return;
    }
    setBusy("logout");
    setMessage("正在退出登录...");
    try {
      await readJson(
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        })
      );
      setAccessToken("");
      setSessionInfo(null);
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(authStorageKey);
      }
      setMessage("已退出登录");
      await reloadAll(selectedGroupId, "");
    } catch (error) {
      setMessage(error.message || "退出登录失败");
    } finally {
      setBusy("");
    }
  }

  async function createUser(event) {
    event.preventDefault();
    setBusy("user");
    setMessage("正在创建用户...");
    try {
      const data = await readJson(
        await authFetch("/api/users", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(userForm),
        })
      );
      setUserForm({ username: "", password: "", display_name: "", role: "admin", status: "active" });
      setMessage(`用户已创建：${data.item.display_name}`);
      await reloadAll(selectedGroupId);
    } catch (error) {
      setMessage(error.message || "创建用户失败");
    } finally {
      setBusy("");
    }
  }

  async function createGroup(event) {
    event.preventDefault();
    setBusy("group");
    setMessage("正在创建账号组...");
    try {
      const payload = {
        ...groupForm,
        owner_user_id: groupForm.owner_user_id ? Number(groupForm.owner_user_id) : null,
      };
      const data = await readJson(
        await authFetch("/api/groups", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      );
      setSelectedGroupId(String(data.item.id));
      setGroupForm({ group_name: "", group_code: "", owner_user_id: "", status: "active", remark: "" });
      setMessage(`账号组已创建：${data.item.group_name}`);
      await reloadAll(String(data.item.id));
    } catch (error) {
      setMessage(error.message || "创建账号组失败");
    } finally {
      setBusy("");
    }
  }

  async function createGroupMember(event) {
    event.preventDefault();
    if (!selectedGroupId) {
      setMessage("请先选择账号组");
      return;
    }
    setBusy("member");
    setMessage("正在添加账号组成员...");
    try {
      const data = await readJson(
        await authFetch(`/api/groups/${selectedGroupId}/members`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: Number(memberForm.user_id),
            member_role: memberForm.member_role,
          }),
        })
      );
      setMemberForm({ user_id: "", member_role: "editor" });
      setMessage(`成员已加入账号组：${data.item.user?.display_name || data.item.user_id}`);
      await reloadAll(selectedGroupId);
    } catch (error) {
      setMessage(error.message || "添加账号组成员失败");
    } finally {
      setBusy("");
    }
  }

  async function issueWorkerToken(event) {
    event.preventDefault();
    setBusy("worker-token");
    setMessage("正在创建 Worker Token...");
    try {
      const payload = {
        ...workerTokenForm,
        group_id: workerTokenForm.group_id ? Number(workerTokenForm.group_id) : null,
        issued_by_user_id: workerTokenForm.issued_by_user_id ? Number(workerTokenForm.issued_by_user_id) : null,
        expire_days: Number(workerTokenForm.expire_days || 30),
      };
      const data = await readJson(
        await authFetch("/api/worker-tokens", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      );
      setLastIssuedToken(data.item.plain_token || "");
      setMessage(`Worker Token 已创建：${data.item.worker_code}`);
      await reloadAll(selectedGroupId);
    } catch (error) {
      setMessage(error.message || "创建 Worker Token 失败");
    } finally {
      setBusy("");
    }
  }

  async function revokeToken(tokenId) {
    setBusy(`revoke-${tokenId}`);
    setMessage(`正在吊销 Worker Token #${tokenId}...`);
    try {
      await readJson(
        await authFetch(`/api/worker-tokens/${tokenId}/revoke`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: "manual_revoke" }),
        })
      );
      setMessage(`Worker Token #${tokenId} 已吊销`);
      await reloadAll(selectedGroupId);
    } catch (error) {
      setMessage(error.message || "吊销 Worker Token 失败");
    } finally {
      setBusy("");
    }
  }

  const summaryCards = [
    { label: "用户数", value: String(users.length), hint: "平台用户", ok: users.length > 0 },
    { label: "账号组", value: String(groups.length), hint: "业务隔离", ok: groups.length > 0 },
    {
      label: "有效 Token",
      value: String(workerTokens.filter((item) => item.status === "active").length),
      hint: "Worker 凭证",
      ok: workerTokens.some((item) => item.status === "active"),
    },
    {
      label: "登录态",
      value: sessionInfo?.user?.display_name || "未登录",
      hint: sessionInfo?.session?.expired_at ? `过期 ${formatDate(sessionInfo.session.expired_at)}` : "等待正式登录",
      ok: !!sessionInfo?.user,
    },
  ];

  return (
    <DashboardShell
      title="访问控制"
      description="这里已经从骨架推进到正式登录、Worker Token 注册和任务执行记录，后面可以继续往统一鉴权与权限模型扩展。"
      action={
        <button type="button" style={buttonStyle} onClick={() => reloadAll(selectedGroupId, accessToken)}>
          刷新数据
        </button>
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

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(320px, 380px) minmax(0, 1fr)",
          gap: 16,
        }}
      >
        <Section title="正式登录" hint="先把账号密码会话接通，后面再把页面级鉴权彻底收口。">
          {sessionInfo?.user ? (
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ fontSize: 14, color: "#e2e8f0" }}>当前用户：{sessionInfo.user.display_name}</div>
              <div style={{ fontSize: 13, color: "#94a3b8" }}>账号：{sessionInfo.user.username}</div>
              <div style={{ fontSize: 13, color: "#94a3b8" }}>角色：{sessionInfo.user.role}</div>
              <div style={{ fontSize: 13, color: "#94a3b8" }}>
                会话过期：{formatDate(sessionInfo.session?.expired_at)}
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button type="button" style={secondaryButtonStyle} onClick={() => loadSession(accessToken)}>
                  刷新会话
                </button>
                <button type="button" style={buttonStyle} disabled={busy === "logout"} onClick={logout}>
                  {busy === "logout" ? "退出中..." : "退出登录"}
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={login} style={{ display: "grid", gap: 12 }}>
              <input
                style={inputStyle}
                value={loginForm.username}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, username: e.target.value }))}
                placeholder="用户名"
              />
              <input
                style={inputStyle}
                type="password"
                value={loginForm.password}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, password: e.target.value }))}
                placeholder="密码"
              />
              <button style={buttonStyle} disabled={busy === "login"}>
                {busy === "login" ? "登录中..." : "登录"}
              </button>
            </form>
          )}
        </Section>

        <Section title="任务执行记录" hint="这里记录 Worker 领取、完成、失败和重试，方便追执行轨迹。">
          <div style={{ overflowX: "auto", maxHeight: 320 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>任务</th>
                  <th style={tableHeadStyle}>事件</th>
                  <th style={tableHeadStyle}>Worker</th>
                  <th style={tableHeadStyle}>状态变化</th>
                  <th style={tableHeadStyle}>时间</th>
                </tr>
              </thead>
              <tbody>
                {taskExecutions.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      还没有任务执行记录。
                    </td>
                  </tr>
                ) : (
                  taskExecutions.map((item) => (
                    <tr key={item.id}>
                      <td style={tableCellStyle}>#{item.task_id}</td>
                      <td style={tableCellStyle}>
                        <div>{item.event_type}</div>
                        {item.error_message ? (
                          <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>{item.error_message}</div>
                        ) : null}
                      </td>
                      <td style={tableCellStyle}>{item.worker_code || "-"}</td>
                      <td style={tableCellStyle}>
                        {item.status_before || "-"} -&gt; {item.status_after || "-"}
                      </td>
                      <td style={tableCellStyle}>{formatDate(item.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(320px, 380px) minmax(320px, 380px) minmax(0, 1fr)",
          gap: 16,
        }}
      >
        <Section title="创建用户" hint="第一版先走本地账号密码，后面再接统一权限收敛。">
          <form onSubmit={createUser} style={{ display: "grid", gap: 12 }}>
            <input style={inputStyle} value={userForm.username} onChange={(e) => setUserForm((p) => ({ ...p, username: e.target.value }))} placeholder="用户名" />
            <input style={inputStyle} type="password" value={userForm.password} onChange={(e) => setUserForm((p) => ({ ...p, password: e.target.value }))} placeholder="密码，至少 6 位" />
            <input style={inputStyle} value={userForm.display_name} onChange={(e) => setUserForm((p) => ({ ...p, display_name: e.target.value }))} placeholder="显示名称" />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <select style={inputStyle} value={userForm.role} onChange={(e) => setUserForm((p) => ({ ...p, role: e.target.value }))}>
                {["admin", "manager", "operator", "viewer"].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <select style={inputStyle} value={userForm.status} onChange={(e) => setUserForm((p) => ({ ...p, status: e.target.value }))}>
                {["active", "disabled"].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </div>
            <button style={buttonStyle} disabled={busy === "user"}>{busy === "user" ? "创建中..." : "创建用户"}</button>
          </form>
        </Section>

        <Section title="创建账号组" hint="后面任务、平台账号和 Worker Token 都会挂到组上。">
          <form onSubmit={createGroup} style={{ display: "grid", gap: 12 }}>
            <input style={inputStyle} value={groupForm.group_name} onChange={(e) => setGroupForm((p) => ({ ...p, group_name: e.target.value }))} placeholder="账号组名称" />
            <input style={inputStyle} value={groupForm.group_code} onChange={(e) => setGroupForm((p) => ({ ...p, group_code: e.target.value }))} placeholder="账号组编码，可留空自动生成" />
            <select style={inputStyle} value={groupForm.owner_user_id} onChange={(e) => setGroupForm((p) => ({ ...p, owner_user_id: e.target.value }))}>
              <option value="">选择组负责人（可留空）</option>
              {userOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <select style={inputStyle} value={groupForm.status} onChange={(e) => setGroupForm((p) => ({ ...p, status: e.target.value }))}>
              {["active", "disabled"].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
            <textarea style={{ ...inputStyle, minHeight: 90, resize: "vertical" }} value={groupForm.remark} onChange={(e) => setGroupForm((p) => ({ ...p, remark: e.target.value }))} placeholder="备注" />
            <button style={buttonStyle} disabled={busy === "group"}>{busy === "group" ? "创建中..." : "创建账号组"}</button>
          </form>
        </Section>

        <Section title="签发 Worker Token" hint="给 Worker.exe 的正式凭证，启动时先注册再领任务。">
          <form onSubmit={issueWorkerToken} style={{ display: "grid", gap: 12 }}>
            <input style={inputStyle} value={workerTokenForm.worker_code} onChange={(e) => setWorkerTokenForm((p) => ({ ...p, worker_code: e.target.value }))} placeholder="Worker Code" />
            <input style={inputStyle} value={workerTokenForm.token_name} onChange={(e) => setWorkerTokenForm((p) => ({ ...p, token_name: e.target.value }))} placeholder="Token 名称" />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <select style={inputStyle} value={workerTokenForm.group_id} onChange={(e) => setWorkerTokenForm((p) => ({ ...p, group_id: e.target.value }))}>
                <option value="">绑定账号组（可留空）</option>
                {groups.map((item) => <option key={item.id} value={item.id}>{item.group_name}</option>)}
              </select>
              <select style={inputStyle} value={workerTokenForm.issued_by_user_id} onChange={(e) => setWorkerTokenForm((p) => ({ ...p, issued_by_user_id: e.target.value }))}>
                <option value="">签发人（可留空）</option>
                {userOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </div>
            <input style={inputStyle} type="number" min="1" max="3650" value={workerTokenForm.expire_days} onChange={(e) => setWorkerTokenForm((p) => ({ ...p, expire_days: e.target.value }))} placeholder="有效天数" />
            <button style={buttonStyle} disabled={busy === "worker-token"}>{busy === "worker-token" ? "签发中..." : "签发 Token"}</button>
            {lastIssuedToken ? (
              <div style={{ fontSize: 12, color: "#fcd34d", lineHeight: 1.6, wordBreak: "break-all" }}>
                最新明文 Token：{lastIssuedToken}
              </div>
            ) : null}
          </form>
        </Section>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(360px, 420px)",
          gap: 16,
        }}
      >
        <Section title="用户与账号组" hint="先把身份和分组建立起来。">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>用户</th>
                  <th style={tableHeadStyle}>角色</th>
                  <th style={tableHeadStyle}>状态</th>
                  <th style={tableHeadStyle}>最近登录</th>
                </tr>
              </thead>
              <tbody>
                {users.map((item) => (
                  <tr key={item.id}>
                    <td style={tableCellStyle}>
                      <div>{item.display_name}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{item.username}</div>
                    </td>
                    <td style={tableCellStyle}>{item.role}</td>
                    <td style={tableCellStyle}>{item.status}</td>
                    <td style={tableCellStyle}>{formatDate(item.last_login_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ height: 16 }} />

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>账号组</th>
                  <th style={tableHeadStyle}>编码</th>
                  <th style={tableHeadStyle}>状态</th>
                  <th style={tableHeadStyle}>负责人</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((item) => (
                  <tr key={item.id}>
                    <td style={tableCellStyle}>{item.group_name}</td>
                    <td style={tableCellStyle}>{item.group_code}</td>
                    <td style={tableCellStyle}>{item.status}</td>
                    <td style={tableCellStyle}>{users.find((user) => user.id === item.owner_user_id)?.display_name || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="账号组成员" hint="选一个组，给它补成员和角色。">
          <div style={{ display: "grid", gap: 12 }}>
            <select style={inputStyle} value={selectedGroupId} onChange={(e) => setSelectedGroupId(e.target.value)}>
              <option value="">选择账号组</option>
              {groups.map((item) => <option key={item.id} value={item.id}>{item.group_name}</option>)}
            </select>
            <form onSubmit={createGroupMember} style={{ display: "grid", gap: 12 }}>
              <select style={inputStyle} value={memberForm.user_id} onChange={(e) => setMemberForm((p) => ({ ...p, user_id: e.target.value }))}>
                <option value="">选择用户</option>
                {userOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <select style={inputStyle} value={memberForm.member_role} onChange={(e) => setMemberForm((p) => ({ ...p, member_role: e.target.value }))}>
                {["owner", "manager", "editor", "viewer"].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <button style={secondaryButtonStyle} disabled={busy === "member"}>{busy === "member" ? "添加中..." : "添加成员"}</button>
            </form>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={tableHeadStyle}>成员</th>
                    <th style={tableHeadStyle}>角色</th>
                    <th style={tableHeadStyle}>加入时间</th>
                  </tr>
                </thead>
                <tbody>
                  {groupMembers.length === 0 ? (
                    <tr>
                      <td colSpan={3} style={{ ...tableCellStyle, color: "#94a3b8" }}>当前账号组还没有成员。</td>
                    </tr>
                  ) : (
                    groupMembers.map((item) => (
                      <tr key={item.id}>
                        <td style={tableCellStyle}>{item.user?.display_name || item.user_id}</td>
                        <td style={tableCellStyle}>{item.member_role}</td>
                        <td style={tableCellStyle}>{formatDate(item.created_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Section>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
          gap: 16,
        }}
      >
        <Section title="Worker Token 列表" hint="明文只在签发时显示一次，后面只保留状态和过期信息。">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>Worker</th>
                  <th style={tableHeadStyle}>名称</th>
                  <th style={tableHeadStyle}>状态</th>
                  <th style={tableHeadStyle}>最近使用</th>
                  <th style={tableHeadStyle}>过期时间</th>
                  <th style={tableHeadStyle}>操作</th>
                </tr>
              </thead>
              <tbody>
                {workerTokens.map((item) => (
                  <tr key={item.id}>
                    <td style={tableCellStyle}>{item.worker_code}</td>
                    <td style={tableCellStyle}>{item.token_name}</td>
                    <td style={tableCellStyle}>{item.status}</td>
                    <td style={tableCellStyle}>{formatDate(item.last_used_at)}</td>
                    <td style={tableCellStyle}>{formatDate(item.expired_at)}</td>
                    <td style={tableCellStyle}>
                      <button
                        type="button"
                        style={secondaryButtonStyle}
                        disabled={busy === `revoke-${item.id}` || item.status !== "active"}
                        onClick={() => revokeToken(item.id)}
                      >
                        {busy === `revoke-${item.id}` ? "吊销中..." : "吊销"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="审计日志" hint="登录、退出、建用户、建组、签发 Token、Worker 注册都会进入审计。">
          <div style={{ overflowX: "auto", maxHeight: 420 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>动作</th>
                  <th style={tableHeadStyle}>目标</th>
                  <th style={tableHeadStyle}>发起方</th>
                  <th style={tableHeadStyle}>时间</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((item) => (
                  <tr key={item.id}>
                    <td style={tableCellStyle}>{item.action}</td>
                    <td style={tableCellStyle}>{item.target_type}:{item.target_id}</td>
                    <td style={tableCellStyle}>{item.actor_type}{item.actor_code ? ` / ${item.actor_code}` : ""}</td>
                    <td style={tableCellStyle}>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </section>

      <Section title="当前消息" hint="最近一次登录、创建、签发或刷新结果。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>
    </DashboardShell>
  );
}
