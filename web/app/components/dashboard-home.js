"use client";

import { useEffect, useState } from "react";
import {
  DashboardShell,
  EntryCard,
  Section,
  SummaryCard,
  buttonStyle,
  readJson,
} from "./dashboard-ui";

export default function DashboardHome() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "未配置";
  const [health, setHealth] = useState({ loading: true, ok: false, detail: "" });
  const [summary, setSummary] = useState({
    total_asset_records: 0,
    pending_tasks: 0,
    online_workers: 0,
    bucket: "",
    latest_asset_record: null,
    latest_task: null,
    latest_worker: null,
    storage_configured: false,
    database_configured: false,
  });
  const [taskSummary, setTaskSummary] = useState({
    total: 0,
    pending: 0,
    running: 0,
    success: 0,
    failed: 0,
  });
  const [workerSummary, setWorkerSummary] = useState({
    total: 0,
    online: 0,
    offline: 0,
    latest: null,
  });
  const [message, setMessage] = useState("已就绪");

  async function loadHealth() {
    setHealth({ loading: true, ok: false, detail: "" });
    try {
      const data = await readJson(await fetch("/api/health", { cache: "no-store" }));
      setHealth({
        loading: false,
        ok: !!data.ok,
        detail: data.detail || JSON.stringify(data),
      });
    } catch (error) {
      setHealth({
        loading: false,
        ok: false,
        detail: error.message || "请求失败",
      });
    }
  }

  async function loadSummary() {
    try {
      const data = await readJson(await fetch("/api/dashboard/summary", { cache: "no-store" }));
      setSummary(data);
    } catch (error) {
      setMessage(error.message || "获取系统摘要失败");
    }
  }

  async function loadTaskSummary() {
    try {
      const data = await readJson(await fetch("/api/tasks/summary", { cache: "no-store" }));
      setTaskSummary(data);
    } catch (error) {
      setMessage(error.message || "获取任务摘要失败");
    }
  }

  async function loadWorkerSummary() {
    try {
      const data = await readJson(await fetch("/api/workers/summary", { cache: "no-store" }));
      setWorkerSummary(data);
    } catch (error) {
      setMessage(error.message || "获取 Worker 摘要失败");
    }
  }

  async function reloadAll() {
    setMessage("正在刷新首页摘要...");
    await Promise.all([loadHealth(), loadSummary(), loadTaskSummary(), loadWorkerSummary()]);
    setMessage("首页摘要已刷新");
  }

  useEffect(() => {
    reloadAll();
  }, []);

  const summaryCards = [
    {
      label: "服务状态",
      value: health.loading ? "检查中" : health.ok ? "正常" : "异常",
      hint: "API 健康检查",
      ok: health.ok,
    },
    {
      label: "待处理任务",
      value: String(taskSummary.pending || 0),
      hint: "等待分配或领取",
      ok: (taskSummary.pending || 0) > 0,
    },
    {
      label: "在线 Worker",
      value: String(workerSummary.online || 0),
      hint: "当前可执行节点",
      ok: (workerSummary.online || 0) > 0,
    },
    {
      label: "资产记录",
      value: String(summary.total_asset_records || 0),
      hint: summary.bucket || "R2 / 数据库",
      ok: summary.storage_configured,
    },
  ];

  return (
    <DashboardShell
      title="首页总览"
      description="这里只看系统状态、关键摘要和业务入口，不把任务、节点、文件全堆在首页。"
      action={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" style={buttonStyle} onClick={reloadAll}>
            刷新首页
          </button>
          <a
            href="/api/dashboard/summary"
            target="_blank"
            rel="noreferrer"
            style={{ ...buttonStyle, textDecoration: "none", background: "#18213f", border: "1px solid #334155" }}
          >
            查看摘要 JSON
          </a>
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
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 16,
        }}
      >
        <EntryCard
          href="/tasks"
          title="任务中心"
          hint="创建任务、分配 Worker、查看执行状态、处理失败重试。"
          meta={`当前待处理 ${taskSummary.pending || 0} 条，运行中 ${taskSummary.running || 0} 条`}
        />
        <EntryCard
          href="/workers"
          title="Worker 节点"
          hint="查看节点在线状态、心跳时间、当前任务，必要时手动登记测试节点。"
          meta={`在线 ${workerSummary.online || 0} 台，离线 ${workerSummary.offline || 0} 台`}
        />
        <EntryCard
          href="/files"
          title="文件中心"
          hint="上传文本或文件到 R2，查看对象列表和数据库资产记录。"
          meta={`已登记资产 ${summary.total_asset_records || 0} 条`}
        />
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
        }}
      >
        <Section title="当前运行判断" hint="运营视角只看现在是不是能继续推进。">
          <div style={{ display: "grid", gap: 10, fontSize: 14, color: "#cbd5e1" }}>
            <div>API：{health.ok ? "可用" : `异常 - ${health.detail || "待检查"}`}</div>
            <div>数据库：{summary.database_configured ? "已接入" : "未接入"}</div>
            <div>R2：{summary.storage_configured ? `已接入（${summary.bucket || "未命名"}）` : "未接入"}</div>
            <div>当前 API 地址：{apiBaseUrl}</div>
          </div>
        </Section>

        <Section title="最近动态" hint="不用翻大表，也能知道最近系统在发生什么。">
          <div style={{ display: "grid", gap: 10, fontSize: 14, color: "#cbd5e1" }}>
            <div>最新任务：{summary.latest_task?.title || "暂无任务"}</div>
            <div>最新节点：{summary.latest_worker?.display_name || "暂无节点"}</div>
            <div>最新资产：{summary.latest_asset_record?.key || "暂无资产"}</div>
            <div>总任务数：{taskSummary.total || 0}</div>
          </div>
        </Section>
      </section>

      <Section title="当前消息" hint="首页最后一次刷新或异常信息。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>
    </DashboardShell>
  );
}
