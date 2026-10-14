"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const cardStyle = {
  background: "#121933",
  border: "1px solid #26314f",
  borderRadius: 14,
  padding: 16,
};

export const inputStyle = {
  width: "100%",
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 10,
  color: "#e5e7eb",
  padding: "10px 12px",
  fontSize: 14,
  boxSizing: "border-box",
};

export const buttonStyle = {
  background: "#4f46e5",
  color: "#fff",
  border: 0,
  borderRadius: 10,
  padding: "10px 14px",
  fontSize: 14,
  cursor: "pointer",
};

export const secondaryButtonStyle = {
  ...buttonStyle,
  background: "#18213f",
  border: "1px solid #334155",
};

export const taskStatusOptions = ["pending", "queued", "running", "success", "failed", "cancelled"];

const navItems = [
  { href: "/", label: "首页总览", hint: "只看状态和入口" },
  { href: "/tasks", label: "任务中心", hint: "创建、分配、重试" },
  { href: "/workers", label: "Worker 节点", hint: "节点在线、心跳、状态" },
  { href: "/files", label: "文件中心", hint: "R2 文件和数据库记录" },
];

export function formatDate(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export async function readJson(response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

export function StatusPill({ ok, text }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 999,
        fontSize: 12,
        background: ok ? "rgba(34,197,94,.14)" : "rgba(239,68,68,.14)",
        color: ok ? "#86efac" : "#fca5a5",
        border: `1px solid ${ok ? "rgba(34,197,94,.3)" : "rgba(239,68,68,.3)"}`,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 999,
          background: ok ? "#22c55e" : "#ef4444",
        }}
      />
      {text}
    </span>
  );
}

export function SummaryCard({ label, value, hint, ok = true }) {
  return (
    <div style={{ ...cardStyle, padding: 14 }}>
      <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 10 }}>{value}</div>
      <StatusPill ok={ok} text={hint} />
    </div>
  );
}

export function EntryCard({ href, title, hint, meta }) {
  return (
    <Link
      href={href}
      style={{
        ...cardStyle,
        textDecoration: "none",
        color: "#e5e7eb",
        display: "grid",
        gap: 10,
        transition: "transform .15s ease, border-color .15s ease",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{title}</div>
        <span style={{ fontSize: 12, color: "#818cf8" }}>进入</span>
      </div>
      <div style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.7 }}>{hint}</div>
      {meta ? <div style={{ fontSize: 13, color: "#cbd5e1" }}>{meta}</div> : null}
    </Link>
  );
}

export function Section({ title, hint, action, children }) {
  return (
    <section style={cardStyle}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
          {hint ? (
            <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>{hint}</div>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      style={{
        ...cardStyle,
        position: "sticky",
        top: 20,
        padding: 12,
        display: "grid",
        gap: 10,
        alignSelf: "start",
      }}
    >
      <div style={{ padding: "10px 10px 6px" }}>
        <div style={{ fontSize: 22, fontWeight: 700 }}>Creator Cockpit</div>
        <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
          首页只看摘要，业务分区独立打开，不再全塞在一页里。
        </div>
      </div>

      {navItems.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            style={{
              textDecoration: "none",
              borderRadius: 12,
              padding: "12px 14px",
              background: active ? "#4f46e5" : "#18213f",
              color: "#fff",
              border: `1px solid ${active ? "#6d64ff" : "#26314f"}`,
              display: "grid",
              gap: 4,
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 600 }}>{item.label}</span>
            <span style={{ fontSize: 12, color: active ? "rgba(255,255,255,.88)" : "#94a3b8" }}>
              {item.hint}
            </span>
          </Link>
        );
      })}
    </aside>
  );
}

export function DashboardShell({ title, description, action, children }) {
  return (
    <main style={{ maxWidth: 1460, margin: "0 auto", padding: 20 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "240px minmax(0, 1fr)",
          gap: 16,
          alignItems: "start",
        }}
      >
        <Sidebar />

        <div style={{ display: "grid", gap: 16 }}>
          <section
            style={{
              ...cardStyle,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <div>
              <h1 style={{ margin: 0, fontSize: 30 }}>{title}</h1>
              <div style={{ marginTop: 8, color: "#94a3b8", fontSize: 14 }}>{description}</div>
            </div>
            {action ? <div>{action}</div> : null}
          </section>

          {children}
        </div>
      </div>
    </main>
  );
}
