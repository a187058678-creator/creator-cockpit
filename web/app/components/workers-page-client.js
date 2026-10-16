"use client";

import { useEffect, useState } from "react";
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

export default function WorkersPageClient() {
  const [workers, setWorkers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [workerGroupFilter, setWorkerGroupFilter] = useState("");
  const [workerSummary, setWorkerSummary] = useState({
    total: 0,
    online: 0,
    offline: 0,
    latest: null,
  });
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [workerForm, setWorkerForm] = useState({
    worker_code: "worker-cn-001",
    display_name: "深圳一号机",
    status: "idle",
    group_id: "",
    machine_info: "Windows 11 / RTX 4060 / Clash",
    capabilities: "yt-dlp,ffmpeg,moviepy,upload-r2",
    current_task_title: "",
    heartbeat_note: "已连接 API，等待拉取任务",
  });

  async function loadWorkers(groupId = workerGroupFilter) {
    try {
      const data = await readJson(
        await authFetch(`/api/workers?group_id=${encodeURIComponent(groupId)}`, { cache: "no-store" })
      );
      setWorkers(data.items || []);
    } catch (error) {
      setWorkers([]);
      setMessage(error.message || "获取 Worker 列表失败");
    }
  }

  async function loadWorkerSummary(groupId = workerGroupFilter) {
    try {
      const data = await readJson(
        await authFetch(`/api/workers/summary?group_id=${encodeURIComponent(groupId)}`, { cache: "no-store" })
      );
      setWorkerSummary(data);
    } catch (error) {
      setMessage(error.message || "获取 Worker 摘要失败");
    }
  }

  async function loadGroups() {
    try {
      const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
      setGroups(data.items || []);
    } catch (error) {
      setGroups([]);
      setMessage(error.message || "获取账号组失败");
    }
  }

  async function reloadAll(groupId = workerGroupFilter) {
    setMessage("正在刷新 Worker 节点...");
    await Promise.all([loadWorkers(groupId), loadWorkerSummary(groupId), loadGroups()]);
    setMessage("Worker 节点已刷新");
  }

  useEffect(() => {
    reloadAll();
  }, []);

  async function submitHeartbeat(event) {
    event.preventDefault();
    setBusy("worker");
    setMessage("正在提交 Worker 心跳...");
    try {
      const data = await readJson(
        await authFetch("/api/workers/heartbeat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...workerForm,
            group_id: workerForm.group_id ? Number(workerForm.group_id) : null,
            capabilities: workerForm.capabilities
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
          }),
        })
      );
      setMessage(`Worker 已更新：${data.item.display_name}`);
      setWorkerGroupFilter(workerForm.group_id || "");
      await reloadAll(workerForm.group_id || "");
    } catch (error) {
      setMessage(error.message || "提交 Worker 心跳失败");
    } finally {
      setBusy("");
    }
  }

  async function deleteWorker(workerCode) {
    const confirmed = window.confirm(`确认删除节点 ${workerCode} 吗？删除后任务分配下拉里也会移除它。`);
    if (!confirmed) {
      return;
    }

    setBusy(`delete-${workerCode}`);
    setMessage(`正在删除节点 ${workerCode}...`);
    try {
      const data = await readJson(
        await authFetch(`/api/workers/${encodeURIComponent(workerCode)}`, {
          method: "DELETE",
        })
      );
      setMessage(`节点 ${workerCode} 已删除，已清理 ${data.cleared_task_count || 0} 条任务指派`);
      await reloadAll();
    } catch (error) {
      setMessage(error.message || "删除 Worker 节点失败");
    } finally {
      setBusy("");
    }
  }

  const summaryCards = [
    {
      label: "节点总数",
      value: String(workerSummary.total || 0),
      hint: "已登记 Worker",
      ok: true,
    },
    {
      label: "在线节点",
      value: String(workerSummary.online || 0),
      hint: "当前可接任务",
      ok: (workerSummary.online || 0) > 0,
    },
    {
      label: "离线节点",
      value: String(workerSummary.offline || 0),
      hint: "重点关注心跳超时",
      ok: (workerSummary.offline || 0) === 0,
    },
    {
      label: "最新节点",
      value: workerSummary.latest?.display_name || "暂无",
      hint: workerSummary.latest?.is_timed_out ? "最新节点已超时" : "最近一次心跳",
      ok: !workerSummary.latest?.is_timed_out,
    },
  ];

  return (
    <DashboardShell
      title="Worker 节点"
      description="这里专门看节点在线状态、心跳时间和当前任务，方便判断算力是否可用。"
      action={
        <button type="button" style={buttonStyle} onClick={() => reloadAll()}>
          刷新节点
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
          <SummaryCard
            key={item.label}
            label={item.label}
            value={item.value}
            hint={item.hint}
            ok={item.ok}
          />
        ))}
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(340px, 420px) minmax(0, 1fr)",
          gap: 16,
        }}
      >
        <Section title="登记测试节点" hint="真实 Worker.exe 跑起来后会自动打心跳，这里保留手动登记入口。">
          <form onSubmit={submitHeartbeat} style={{ display: "grid", gap: 12 }}>
            <input
              style={inputStyle}
              value={workerForm.worker_code}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, worker_code: event.target.value }))}
              placeholder="Worker 编号"
            />
            <input
              style={inputStyle}
              value={workerForm.display_name}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, display_name: event.target.value }))}
              placeholder="显示名称"
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <select
                style={inputStyle}
                value={workerForm.group_id}
                onChange={(event) => setWorkerForm((prev) => ({ ...prev, group_id: event.target.value }))}
              >
                <option value="">归属账号组</option>
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.group_name}
                  </option>
                ))}
              </select>
              <input
                style={inputStyle}
                value={workerForm.status}
                onChange={(event) => setWorkerForm((prev) => ({ ...prev, status: event.target.value }))}
                placeholder="状态"
              />
            </div>
            <input
              style={inputStyle}
              value={workerForm.current_task_title}
              onChange={(event) =>
                setWorkerForm((prev) => ({ ...prev, current_task_title: event.target.value }))
              }
              placeholder="当前任务"
            />
            <input
              style={inputStyle}
              value={workerForm.machine_info}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, machine_info: event.target.value }))}
              placeholder="机器信息"
            />
            <input
              style={inputStyle}
              value={workerForm.capabilities}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, capabilities: event.target.value }))}
              placeholder="能力，逗号分隔"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 100, resize: "vertical" }}
              value={workerForm.heartbeat_note}
              onChange={(event) => setWorkerForm((prev) => ({ ...prev, heartbeat_note: event.target.value }))}
              placeholder="心跳备注"
            />
            <button style={buttonStyle} disabled={busy === "worker"}>
              {busy === "worker" ? "提交中..." : "提交 Worker 心跳"}
            </button>
          </form>
        </Section>

        <Section title="节点列表" hint="运营视角默认只看节点、状态、当前任务、心跳时间。">
          <div style={{ marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select
              style={{ ...inputStyle, width: 180 }}
              value={workerGroupFilter}
              onChange={(event) => {
                const nextValue = event.target.value;
                setWorkerGroupFilter(nextValue);
                reloadAll(nextValue);
              }}
            >
              <option value="">全部账号组</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.group_name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={tableHeadStyle}>节点</th>
                  <th style={{ ...tableHeadStyle, width: 120 }}>状态</th>
                  <th style={tableHeadStyle}>当前任务</th>
                  <th style={tableHeadStyle}>备注</th>
                  <th style={{ ...tableHeadStyle, width: 170 }}>最近心跳</th>
                  <th style={{ ...tableHeadStyle, width: 120 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {workers.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                      还没有 Worker 节点。
                    </td>
                  </tr>
                ) : (
                  workers.map((item) => (
                    <tr key={item.id}>
                      <td style={tableCellStyle}>
                        <div>{item.display_name}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          {item.worker_code} / 组 {item.group_id || "-"}
                        </div>
                      </td>
                      <td style={tableCellStyle}>
                        <div>{item.status}</div>
                        {item.is_timed_out ? (
                          <div style={{ marginTop: 4, fontSize: 12, color: "#fca5a5" }}>心跳超时</div>
                        ) : null}
                      </td>
                      <td style={tableCellStyle}>{item.current_task_title || "-"}</td>
                      <td style={tableCellStyle}>{item.heartbeat_note || "-"}</td>
                      <td style={tableCellStyle}>{formatDate(item.last_heartbeat_at)}</td>
                      <td style={tableCellStyle}>
                        <button
                          type="button"
                          style={{
                            ...secondaryButtonStyle,
                            color: "#fca5a5",
                            borderColor: "#7f1d1d",
                          }}
                          onClick={() => deleteWorker(item.worker_code)}
                          disabled={busy === `delete-${item.worker_code}`}
                        >
                          {busy === `delete-${item.worker_code}` ? "删除中..." : "删除节点"}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>
      </section>

      <Section title="当前消息" hint="最近一次节点刷新或心跳提交结果。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>
    </DashboardShell>
  );
}
