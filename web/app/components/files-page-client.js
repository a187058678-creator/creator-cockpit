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

export default function FilesPageClient() {
  const [groups, setGroups] = useState([]);
  const [assetGroupFilter, setAssetGroupFilter] = useState("");
  const [summary, setSummary] = useState({
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

  async function loadSummary() {
    try {
      const data = await readJson(await authFetch("/api/dashboard/summary", { cache: "no-store" }));
      setSummary(data);
    } catch (error) {
      setMessage(error.message || "获取文件摘要失败");
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

  async function loadAssets(prefix = listPrefix, groupId = assetGroupFilter) {
    try {
      const data = await readJson(
        await authFetch(
          `/api/assets/list?prefix=${encodeURIComponent(prefix)}&group_id=${encodeURIComponent(groupId)}`,
          { cache: "no-store" }
        )
      );
      setAssets(data.items || []);
    } catch (error) {
      setAssets([]);
      setMessage(error.message || "获取 R2 文件失败");
    }
  }

  async function loadRecords(prefix = listPrefix, groupId = assetGroupFilter) {
    try {
      const data = await readJson(
        await authFetch(`/api/assets/records?prefix=${encodeURIComponent(prefix)}&group_id=${encodeURIComponent(groupId)}`, {
          cache: "no-store",
        })
      );
      setRecords(data.items || []);
    } catch (error) {
      setRecords([]);
      setMessage(error.message || "获取数据库记录失败");
    }
  }

  async function reloadAll(prefix = listPrefix, groupId = assetGroupFilter) {
    setMessage("正在刷新文件中心...");
    await Promise.all([loadSummary(), loadAssets(prefix, groupId), loadRecords(prefix, groupId), loadGroups()]);
    setMessage("文件中心已刷新");
  }

  useEffect(() => {
    reloadAll("assets");
  }, []);

  async function uploadText(event) {
    event.preventDefault();
    setBusy("text");
    setMessage("正在上传文本...");
    try {
      const data = await readJson(
        await authFetch("/api/assets/text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: textBody,
            prefix: textPrefix,
            filename: textFilename || undefined,
            group_id: assetGroupFilter ? Number(assetGroupFilter) : null,
          }),
        })
      );
      setMessage(`文本上传成功：${data.key}`);
      setListPrefix(textPrefix);
      await reloadAll(textPrefix, assetGroupFilter);
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
      const data = await readJson(
        await authFetch(
          `/api/assets/file?prefix=${encodeURIComponent(filePrefix)}&group_id=${encodeURIComponent(assetGroupFilter)}`,
          {
          method: "POST",
          body: formData,
          }
        )
      );
      setMessage(`文件上传成功：${data.key}`);
      setSelectedFile(null);
      setListPrefix(filePrefix);
      await reloadAll(filePrefix, assetGroupFilter);
    } catch (error) {
      setMessage(error.message || "文件上传失败");
    } finally {
      setBusy("");
    }
  }

  async function createPreviewLink(key) {
    setBusy(`preview-${key}`);
    try {
      const data = await readJson(await authFetch(`/api/assets/presign?key=${encodeURIComponent(key)}`));
      window.open(data.url, "_blank", "noopener,noreferrer");
      setMessage(`已生成预览链接：${key}`);
    } catch (error) {
      setMessage(error.message || "生成预览链接失败");
    } finally {
      setBusy("");
    }
  }

  const summaryCards = [
    {
      label: "资产记录",
      value: String(summary.total_asset_records || 0),
      hint: "数据库已登记文件",
      ok: summary.database_configured,
    },
    {
      label: "R2 桶",
      value: summary.bucket || "未配置",
      hint: "当前对象存储桶",
      ok: summary.storage_configured,
    },
    {
      label: "当前前缀",
      value: listPrefix,
      hint: "列表与记录筛选前缀",
      ok: true,
    },
    {
      label: "最新资产",
      value: summary.latest_asset_record?.id ? `#${summary.latest_asset_record.id}` : "暂无",
      hint: summary.latest_asset_record?.key || "还没有上传记录",
      ok: true,
    },
  ];

  return (
    <DashboardShell
      title="文件中心"
      description="这里专门处理 R2 文件上传、对象列表和数据库资产记录查询。"
      action={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <select
            style={{ ...inputStyle, width: 180 }}
            value={assetGroupFilter}
            onChange={(event) => {
              const nextValue = event.target.value;
              setAssetGroupFilter(nextValue);
              reloadAll(listPrefix, nextValue);
            }}
          >
            <option value="">全部账号组</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.group_name}
              </option>
            ))}
          </select>
          <input
            style={{ ...inputStyle, width: 180 }}
            value={listPrefix}
            onChange={(event) => setListPrefix(event.target.value)}
            placeholder="prefix"
          />
          <button type="button" style={buttonStyle} onClick={() => reloadAll(listPrefix)}>
            刷新文件
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
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 16,
        }}
      >
        <Section title="上传文本到 R2" hint="适合快速验证存储链路是否可用。">
          <form onSubmit={uploadText} style={{ display: "grid", gap: 12 }}>
            <input
              style={inputStyle}
              value={textPrefix}
              onChange={(event) => setTextPrefix(event.target.value)}
              placeholder="prefix，例如 assets"
            />
          <select
            style={inputStyle}
            value={assetGroupFilter}
            onChange={(event) => setAssetGroupFilter(event.target.value)}
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
              value={textFilename}
              onChange={(event) => setTextFilename(event.target.value)}
              placeholder="文件名，可留空"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 120, resize: "vertical" }}
              value={textBody}
              onChange={(event) => setTextBody(event.target.value)}
            />
            <button style={buttonStyle} disabled={busy === "text"}>
              {busy === "text" ? "上传中..." : "上传文本"}
            </button>
          </form>
        </Section>

        <Section title="上传本地文件到 R2" hint="把实际素材或测试文件推到对象存储。">
          <form onSubmit={uploadFile} style={{ display: "grid", gap: 12 }}>
            <input
              style={inputStyle}
              value={filePrefix}
              onChange={(event) => setFilePrefix(event.target.value)}
              placeholder="prefix，例如 assets"
            />
            <select
              style={inputStyle}
              value={assetGroupFilter}
              onChange={(event) => setAssetGroupFilter(event.target.value)}
            >
              <option value="">归属账号组</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.group_name}
                </option>
              ))}
            </select>
            <input
              type="file"
              style={inputStyle}
              onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
            />
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              {selectedFile ? `已选择：${selectedFile.name}` : "请选择一个文件"}
            </div>
            <button style={buttonStyle} disabled={busy === "file"}>
              {busy === "file" ? "上传中..." : "上传文件"}
            </button>
          </form>
        </Section>
      </section>

      <Section title="R2 文件列表" hint="先看对象是否真的进了桶，再决定要不要预览。">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={tableHeadStyle}>R2 文件</th>
                <th style={{ ...tableHeadStyle, width: 120 }}>大小</th>
                <th style={{ ...tableHeadStyle, width: 180 }}>时间</th>
                <th style={{ ...tableHeadStyle, width: 120 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {assets.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                    当前前缀下还没有文件。
                  </td>
                </tr>
              ) : (
                assets.map((item) => (
                  <tr key={item.key}>
                    <td style={{ ...tableCellStyle, wordBreak: "break-all" }}>{item.key}</td>
                    <td style={tableCellStyle}>{item.size}</td>
                    <td style={tableCellStyle}>{formatDate(item.last_modified)}</td>
                    <td style={tableCellStyle}>
                      <button
                        type="button"
                        style={buttonStyle}
                        onClick={() => createPreviewLink(item.key)}
                        disabled={busy === `preview-${item.key}`}
                      >
                        预览
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="数据库资产记录" hint="R2 上传成功后，确认记录是否同步落进数据库。">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                <th style={{ ...tableHeadStyle, width: 100 }}>来源</th>
                <th style={tableHeadStyle}>Key</th>
                <th style={{ ...tableHeadStyle, width: 120 }}>大小</th>
                <th style={{ ...tableHeadStyle, width: 120 }}>状态</th>
              </tr>
            </thead>
            <tbody>
              {records.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                    当前还没有数据库记录。
                  </td>
                </tr>
              ) : (
                records.map((item) => (
                  <tr key={item.id}>
                    <td style={tableCellStyle}>{item.id}</td>
                    <td style={tableCellStyle}>{item.source_type}</td>
                    <td style={{ ...tableCellStyle, wordBreak: "break-all" }}>
                      <div>{item.key}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>组 {item.group_id || "-"}</div>
                    </td>
                    <td style={tableCellStyle}>{item.size_bytes}</td>
                    <td style={tableCellStyle}>{item.status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="当前消息" hint="最近一次上传、查询或预览结果。">
        <div style={{ fontSize: 14, color: "#e2e8f0", wordBreak: "break-word" }}>{message}</div>
      </Section>
    </DashboardShell>
  );
}
