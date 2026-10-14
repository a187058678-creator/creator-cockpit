"use client";

import { useEffect, useMemo, useState } from "react";

const cardStyle = {
  background: "#121933",
  border: "1px solid #26314f",
  borderRadius: 14,
  padding: 16,
};

const inputStyle = {
  width: "100%",
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 10,
  color: "#e5e7eb",
  padding: "10px 12px",
  fontSize: 14,
  boxSizing: "border-box",
};

const buttonStyle = {
  background: "#4f46e5",
  color: "#fff",
  border: 0,
  borderRadius: 10,
  padding: "10px 14px",
  fontSize: 14,
  cursor: "pointer",
};

function StatusBadge({ ok, text }) {
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

function formatDate(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export default function HomePage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "未配置";

  const [health, setHealth] = useState({ loading: true, ok: false, detail: "" });
  const [summary, setSummary] = useState({
    loading: true,
    total_asset_records: 0,
    bucket: "",
    latest_asset_record: null,
    storage_configured: false,
    database_configured: false,
  });
  const [assets, setAssets] = useState([]);
  const [records, setRecords] = useState([]);
  const [listPrefix, setListPrefix] = useState("assets");
  const [textPrefix, setTextPrefix] = useState("assets");
  const [textFilename, setTextFilename] = useState("");
  const [textBody, setTextBody] = useState("hello from creator cockpit");
  const [filePrefix, setFilePrefix] = useState("assets");
  const [selectedFile, setSelectedFile] = useState(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("已就绪");

  const latestAsset = useMemo(() => assets[0], [assets]);

  const statCards = [
    {
      title: "API",
      value: health.loading ? "检查中" : health.ok ? "正常" : "异常",
      hint: "Railway FastAPI 服务",
      ok: health.ok,
    },
    {
      title: "数据库",
      value: summary.database_configured ? "已接入" : "未接入",
      hint: "上传结果落库",
      ok: summary.database_configured,
    },
    {
      title: "R2",
      value: summary.storage_configured ? "已接入" : "未接入",
      hint: summary.bucket || "对象存储",
      ok: summary.storage_configured,
    },
    {
      title: "记录数",
      value: String(summary.total_asset_records || 0),
      hint: "asset_records",
      ok: (summary.total_asset_records || 0) > 0,
    },
  ];

  async function loadHealth() {
    setHealth({ loading: true, ok: false, detail: "" });
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "健康检查失败");
      }
      setHealth({ loading: false, ok: !!data.ok, detail: JSON.stringify(data) });
    } catch (error) {
      setHealth({
        loading: false,
        ok: false,
        detail: error.message || "请求失败",
      });
    }
  }

  async function loadAssets(prefix = listPrefix) {
    try {
      const response = await fetch(
        `/api/assets/list?prefix=${encodeURIComponent(prefix)}`,
        { cache: "no-store" }
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "获取资产失败");
      }
      setAssets(data.items || []);
    } catch (error) {
      setMessage(error.message || "获取资产失败");
      setAssets([]);
    }
  }

  async function loadSummary() {
    try {
      const response = await fetch("/api/dashboard/summary", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "获取摘要失败");
      }
      setSummary({ loading: false, ...data });
    } catch (error) {
      setSummary((prev) => ({
        ...prev,
        loading: false,
      }));
      setMessage(error.message || "获取摘要失败");
    }
  }

  async function loadRecords(prefix = listPrefix) {
    try {
      const response = await fetch(
        `/api/assets/records?prefix=${encodeURIComponent(prefix)}`,
        { cache: "no-store" }
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "获取上传记录失败");
      }
      setRecords(data.items || []);
    } catch (error) {
      setMessage(error.message || "获取上传记录失败");
      setRecords([]);
    }
  }

  useEffect(() => {
    loadHealth();
    loadSummary();
    loadAssets("assets");
    loadRecords("assets");
  }, []);

  async function uploadText(event) {
    event.preventDefault();
    setBusy("text");
    setMessage("正在上传文本文件...");
    try {
      const response = await fetch("/api/assets/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: textBody,
          prefix: textPrefix,
          filename: textFilename || undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "文本上传失败");
      }
      setMessage(`文本上传成功：${data.key}`);
      setListPrefix(textPrefix);
      await loadAssets(textPrefix);
      await loadRecords(textPrefix);
      await loadSummary();
    } catch (error) {
      setMessage(error.message || "文本上传失败");
    } finally {
      setBusy("");
    }
  }

  async function uploadFile(event) {
    event.preventDefault();
    if (!selectedFile) {
      setMessage("请先选择文件");
      return;
    }
    setBusy("file");
    setMessage("正在上传文件...");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const response = await fetch(
        `/api/assets/file?prefix=${encodeURIComponent(filePrefix)}`,
        {
          method: "POST",
          body: formData,
        }
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "文件上传失败");
      }
      setMessage(`文件上传成功：${data.key}`);
      setSelectedFile(null);
      setListPrefix(filePrefix);
      await loadAssets(filePrefix);
      await loadRecords(filePrefix);
      await loadSummary();
    } catch (error) {
      setMessage(error.message || "文件上传失败");
    } finally {
      setBusy("");
    }
  }

  async function createPreviewLink(key) {
    setBusy(key);
    try {
      const response = await fetch(
        `/api/assets/presign?key=${encodeURIComponent(key)}`
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "生成链接失败");
      }
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (error) {
      setMessage(error.message || "生成链接失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <main style={{ maxWidth: 1400, margin: "0 auto", padding: 24 }}>
      <section
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          marginBottom: 20,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 32 }}>Creator Cockpit</h1>
          <p style={{ margin: "8px 0 0", color: "#94a3b8", fontSize: 14 }}>
            管理后台骨架：系统概览、上传测试、R2 资产浏览、数据库记录。
          </p>
        </div>
        <div style={{ ...cardStyle, minWidth: 320 }}>
          <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 8 }}>
            当前 API 地址
          </div>
          <div style={{ fontSize: 13, wordBreak: "break-all" }}>{apiBaseUrl}</div>
        </div>
      </section>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "260px minmax(0, 1fr)",
          gap: 16,
          alignItems: "start",
        }}
      >
        <aside style={{ ...cardStyle, position: "sticky", top: 24 }}>
          <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 14 }}>
            后台导航
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {[
              "系统总览",
              "上传测试",
              "R2 对象列表",
              "数据库记录",
              "任务中心（待接）",
              "Worker 节点（待接）",
            ].map((item, index) => (
              <div
                key={item}
                style={{
                  padding: "10px 12px",
                  borderRadius: 10,
                  background: index < 4 ? "#18213f" : "#10182f",
                  color: index < 4 ? "#e5e7eb" : "#94a3b8",
                  fontSize: 13,
                  border: "1px solid #26314f",
                }}
              >
                {item}
              </div>
            ))}
          </div>
        </aside>

        <div style={{ display: "grid", gap: 16 }}>
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 16,
            }}
          >
            {statCards.map((item) => (
              <div key={item.title} style={cardStyle}>
                <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 10 }}>
                  {item.title}
                </div>
                <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>
                  {item.value}
                </div>
                <StatusBadge ok={item.ok} text={item.hint} />
              </div>
            ))}
          </section>

          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            <div style={cardStyle}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>系统状态</h2>
              <div style={{ fontSize: 13, color: "#cbd5e1", display: "grid", gap: 10 }}>
                <div>健康检查：{health.detail || "等待结果"}</div>
                <div>Bucket：{summary.bucket || "未配置"}</div>
                <div>
                  最新记录：
                  {summary.latest_asset_record
                    ? ` ${summary.latest_asset_record.key}`
                    : " 暂无"}
                </div>
                <div>最新时间：{formatDate(summary.latest_asset_record?.created_at)}</div>
              </div>
              <div style={{ marginTop: 12 }}>
                <button
                  style={buttonStyle}
                  onClick={() => {
                    loadHealth();
                    loadSummary();
                  }}
                >
                  刷新系统状态
                </button>
              </div>
            </div>

            <div style={cardStyle}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>当前消息</h2>
              <div style={{ fontSize: 13, color: "#e2e8f0", wordBreak: "break-word" }}>
                {message}
              </div>
              <div style={{ marginTop: 16, fontSize: 12, color: "#94a3b8" }}>
                最近对象：{latestAsset ? latestAsset.key : "暂无"}
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>
                最近大小：{latestAsset ? `${latestAsset.size} bytes` : "-"}
              </div>
            </div>

            <div style={cardStyle}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>待扩展模块</h2>
              <div style={{ display: "grid", gap: 8, fontSize: 13, color: "#cbd5e1" }}>
                <div>1. 任务创建与队列调度</div>
                <div>2. Worker 心跳与任务拉取</div>
                <div>3. 账号组 / OAuth / 发布编排</div>
                <div>4. 发布记录、审计日志、评论中心</div>
              </div>
            </div>
          </section>

          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
              gap: 16,
              alignItems: "start",
            }}
          >
            <form style={cardStyle} onSubmit={uploadText}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>文本上传</h2>
              <div style={{ display: "grid", gap: 12 }}>
                <input
                  style={inputStyle}
                  value={textPrefix}
                  onChange={(e) => setTextPrefix(e.target.value)}
                  placeholder="prefix，例如 assets"
                />
                <input
                  style={inputStyle}
                  value={textFilename}
                  onChange={(e) => setTextFilename(e.target.value)}
                  placeholder="文件名，可留空自动生成"
                />
                <textarea
                  style={{ ...inputStyle, minHeight: 140, resize: "vertical" }}
                  value={textBody}
                  onChange={(e) => setTextBody(e.target.value)}
                  placeholder="输入要上传的文本内容"
                />
                <button style={buttonStyle} disabled={busy === "text"}>
                  {busy === "text" ? "上传中..." : "上传文本到 R2"}
                </button>
              </div>
            </form>

            <form style={cardStyle} onSubmit={uploadFile}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>文件上传</h2>
              <div style={{ display: "grid", gap: 12 }}>
                <input
                  style={inputStyle}
                  value={filePrefix}
                  onChange={(e) => setFilePrefix(e.target.value)}
                  placeholder="prefix，例如 assets"
                />
                <input
                  type="file"
                  style={inputStyle}
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
                <div style={{ fontSize: 12, color: "#94a3b8" }}>
                  {selectedFile
                    ? `已选择：${selectedFile.name}`
                    : "请选择一个本地文件上传到 R2"}
                </div>
                <button style={buttonStyle} disabled={busy === "file"}>
                  {busy === "file" ? "上传中..." : "上传文件到 R2"}
                </button>
              </div>
            </form>
          </section>

          <section style={cardStyle}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>R2 资产列表</h2>
                <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>
                  查看指定前缀下的对象，并生成预览下载链接。
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input
                  style={{ ...inputStyle, width: 220 }}
                  value={listPrefix}
                  onChange={(e) => setListPrefix(e.target.value)}
                  placeholder="prefix"
                />
                <button
                  style={buttonStyle}
                  onClick={() => {
                    loadAssets(listPrefix);
                    loadRecords(listPrefix);
                  }}
                >
                  刷新列表
                </button>
              </div>
            </div>

            <div style={{ marginTop: 16, overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 13,
                }}
              >
                <thead>
                  <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                    <th style={{ padding: "10px 8px" }}>Key</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>大小</th>
                    <th style={{ padding: "10px 8px", width: 220 }}>更新时间</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.length === 0 ? (
                    <tr>
                      <td
                        colSpan={4}
                        style={{
                          padding: "14px 8px",
                          color: "#94a3b8",
                          borderTop: "1px solid #26314f",
                        }}
                      >
                        当前前缀下暂无对象。
                      </td>
                    </tr>
                  ) : (
                    assets.map((item) => (
                      <tr key={item.key}>
                        <td
                          style={{
                            padding: "12px 8px",
                            borderTop: "1px solid #26314f",
                            wordBreak: "break-all",
                          }}
                        >
                          {item.key}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {item.size}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {formatDate(item.last_modified)}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          <button
                            style={buttonStyle}
                            onClick={() => createPreviewLink(item.key)}
                            disabled={busy === item.key}
                          >
                            {busy === item.key ? "生成中..." : "预览"}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section style={cardStyle}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>数据库上传记录</h2>
                <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>
                  这里的数据来自 Postgres 的 asset_records。
                </div>
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                当前前缀：{listPrefix}
              </div>
            </div>

            <div style={{ marginTop: 16, overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 13,
                }}
              >
                <thead>
                  <tr style={{ textAlign: "left", color: "#94a3b8" }}>
                    <th style={{ padding: "10px 8px", width: 70 }}>ID</th>
                    <th style={{ padding: "10px 8px", width: 100 }}>来源</th>
                    <th style={{ padding: "10px 8px" }}>Key</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>大小</th>
                    <th style={{ padding: "10px 8px", width: 120 }}>状态</th>
                    <th style={{ padding: "10px 8px", width: 220 }}>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        style={{
                          padding: "14px 8px",
                          color: "#94a3b8",
                          borderTop: "1px solid #26314f",
                        }}
                      >
                        当前前缀下暂无数据库记录。
                      </td>
                    </tr>
                  ) : (
                    records.map((item) => (
                      <tr key={item.id}>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {item.id}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {item.source_type}
                        </td>
                        <td
                          style={{
                            padding: "12px 8px",
                            borderTop: "1px solid #26314f",
                            wordBreak: "break-all",
                          }}
                        >
                          {item.key}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {item.size_bytes}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {item.status}
                        </td>
                        <td style={{ padding: "12px 8px", borderTop: "1px solid #26314f" }}>
                          {formatDate(item.created_at)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
