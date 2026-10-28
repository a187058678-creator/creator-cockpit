"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  DashboardShell,
  Section,
  SummaryCard,
  authFetch,
  buttonStyle,
  cardStyle,
  formatDate,
  inputStyle,
  readJson,
  secondaryButtonStyle,
} from "./dashboard-ui";

const tableHeadStyle = {
  padding: "10px 8px",
  textAlign: "left",
  color: "#94a3b8",
  fontSize: 12,
  fontWeight: 600,
};

const tableCellStyle = {
  padding: "10px 8px",
  borderTop: "1px solid #26314f",
  verticalAlign: "top",
  fontSize: 13,
};

function StatusTag({ status }) {
  const palette = {
    active: { bg: "rgba(34,197,94,.14)", border: "rgba(34,197,94,.35)", color: "#86efac" },
    paused: { bg: "rgba(245,158,11,.14)", border: "rgba(245,158,11,.35)", color: "#fcd34d" },
    archived: { bg: "rgba(100,116,139,.14)", border: "rgba(100,116,139,.35)", color: "#cbd5e1" },
  };
  const current = palette[status] || palette.active;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        borderRadius: 999,
        padding: "4px 10px",
        border: `1px solid ${current.border}`,
        background: current.bg,
        color: current.color,
        fontSize: 12,
        lineHeight: 1,
      }}
    >
      {status || "-"}
    </span>
  );
}

export default function AgentFlowProjectsPageClient() {
  const [groups, setGroups] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectRuns, setProjectRuns] = useState([]);
  const [groupFilter, setGroupFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [message, setMessage] = useState("已就绪");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({
    group_id: "",
    project_name: "",
    template_id: "",
    platform: "tiktok",
    subject_domain: "",
    remark: "",
  });

  const selectedProject = useMemo(
    () => projects.find((item) => String(item.id) === String(selectedProjectId)) || null,
    [projects, selectedProjectId]
  );

  async function loadGroups() {
    const data = await readJson(await authFetch("/api/groups", { cache: "no-store" }));
    setGroups(data.items || []);
  }

  async function loadTemplates(groupId = groupFilter) {
    const data = await readJson(
      await authFetch(`/api/agent-flow/templates?group_id=${encodeURIComponent(groupId)}`, { cache: "no-store" })
    );
    setTemplates(data.items || []);
  }

  async function loadProjects(nextGroupId = groupFilter, nextStatus = statusFilter) {
    const data = await readJson(
      await authFetch(
        `/api/agent-flow/projects?group_id=${encodeURIComponent(nextGroupId)}&status=${encodeURIComponent(nextStatus)}`,
        { cache: "no-store" }
      )
    );
    const items = data.items || [];
    setProjects(items);
    setSelectedProjectId((prev) => {
      const matched = items.find((item) => String(item.id) === String(prev));
      return matched ? String(matched.id) : String(items[0]?.id || "");
    });
  }

  async function loadProjectRuns(projectId = selectedProjectId) {
    if (!projectId) {
      setProjectRuns([]);
      return;
    }
    const data = await readJson(await authFetch(`/api/agent-flow/projects/${projectId}/runs`, { cache: "no-store" }));
    setProjectRuns(data.items || []);
  }

  async function reload(nextGroupId = groupFilter, nextStatus = statusFilter) {
    setMessage("正在刷新项目库...");
    try {
      await Promise.all([loadGroups(), loadTemplates(nextGroupId), loadProjects(nextGroupId, nextStatus)]);
      setMessage("项目库已刷新");
    } catch (error) {
      setMessage(error.message || "刷新项目库失败");
    }
  }

  useEffect(() => {
    reload("", "");
  }, []);

  useEffect(() => {
    loadProjectRuns(selectedProjectId).catch((error) => setMessage(error.message || "获取项目运行失败"));
  }, [selectedProjectId]);

  async function createProject(event) {
    event.preventDefault();
    setBusy("create");
    setMessage("正在创建项目...");
    try {
      await readJson(
        await authFetch("/api/agent-flow/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            group_id: form.group_id ? Number(form.group_id) : null,
            project_name: form.project_name,
            template_id: form.template_id ? Number(form.template_id) : null,
            platform: form.platform,
            subject_domain: form.subject_domain,
            remark: form.remark,
          }),
        })
      );
      await reload(groupFilter, statusFilter);
      setForm((prev) => ({ ...prev, project_name: "", subject_domain: "", remark: "" }));
    } catch (error) {
      setMessage(error.message || "创建项目失败");
    } finally {
      setBusy("");
    }
  }

  const cards = [
    { label: "项目总数", value: String(projects.length), hint: "当前系列化项目", ok: true },
    { label: "当前项目", value: selectedProject?.project_name || "-", hint: "当前选中项目", ok: Boolean(selectedProject) },
    { label: "运行数量", value: String(projectRuns.length), hint: "当前项目最近运行", ok: projectRuns.length > 0 },
  ];

  return (
    <DashboardShell
      title="AI文案项目库"
      description="项目库用来组织系列化内容生产，把多次运行挂到同一个长期运营单元下。"
      action={
        <div style={{ display: "grid", gap: 10, minWidth: "min(100%, 640px)" }}>
          <div
            style={{
              padding: "8px 12px",
              borderRadius: 10,
              border: "1px solid #26314f",
              background: "#0f172a",
              color: "#cbd5e1",
              fontSize: 13,
            }}
          >
            当前消息：{message}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <select
              style={{ ...inputStyle, width: 180 }}
              value={groupFilter}
              onChange={(event) => {
                const value = event.target.value;
                setGroupFilter(value);
                reload(value, statusFilter);
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
              value={statusFilter}
              onChange={(event) => {
                const value = event.target.value;
                setStatusFilter(value);
                reload(groupFilter, value);
              }}
            >
              <option value="">全部状态</option>
              {["active", "paused", "archived"].map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
            <Link href="/agent-flow" style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
              返回工作台
            </Link>
            <button type="button" style={buttonStyle} onClick={() => reload(groupFilter, statusFilter)}>
              刷新页面
            </button>
          </div>
        </div>
      }
    >
      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
        {cards.map((item) => (
          <SummaryCard key={item.label} label={item.label} value={item.value} hint={item.hint} ok={item.ok} />
        ))}
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(360px, 460px) minmax(0, 1fr)", gap: 16 }}>
        <Section title="新建项目" hint="先做轻量项目库，后面再补更细的项目设置。">
          <form onSubmit={createProject} style={{ display: "grid", gap: 12 }}>
            <select
              style={inputStyle}
              value={form.group_id}
              onChange={(event) => setForm((prev) => ({ ...prev, group_id: event.target.value }))}
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
              value={form.project_name}
              onChange={(event) => setForm((prev) => ({ ...prev, project_name: event.target.value }))}
              placeholder="项目名称"
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <select
                style={inputStyle}
                value={form.template_id}
                onChange={(event) => setForm((prev) => ({ ...prev, template_id: event.target.value }))}
              >
                <option value="">默认模板</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.template_name}
                  </option>
                ))}
              </select>
              <input
                style={inputStyle}
                value={form.platform}
                onChange={(event) => setForm((prev) => ({ ...prev, platform: event.target.value }))}
                placeholder="主平台"
              />
            </div>
            <input
              style={inputStyle}
              value={form.subject_domain}
              onChange={(event) => setForm((prev) => ({ ...prev, subject_domain: event.target.value }))}
              placeholder="题材域 / 系列方向"
            />
            <textarea
              style={{ ...inputStyle, minHeight: 96, resize: "vertical" }}
              value={form.remark}
              onChange={(event) => setForm((prev) => ({ ...prev, remark: event.target.value }))}
              placeholder="备注"
            />
            <button type="submit" style={buttonStyle} disabled={busy === "create"}>
              {busy === "create" ? "创建中..." : "创建项目"}
            </button>
          </form>
        </Section>

        <Section title="项目详情" hint={selectedProject ? `当前选中项目 #${selectedProject.id}` : "点击左侧项目查看最近运行"}>
          {!selectedProject ? (
            <div style={{ color: "#94a3b8", fontSize: 13 }}>当前还没有选中的项目。</div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{selectedProject.project_name}</div>
                    <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                      编码：{selectedProject.project_code} / 平台：{selectedProject.platform || "-"}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                      模板：{selectedProject.template?.template_name || "-"} / 题材域：{selectedProject.subject_domain || "-"}
                    </div>
                  </div>
                  <StatusTag status={selectedProject.status} />
                </div>
              </div>

              <div style={{ ...cardStyle, padding: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>最近运行</div>
                <div style={{ display: "grid", gap: 8 }}>
                  {projectRuns.length === 0 ? (
                    <div style={{ fontSize: 12, color: "#94a3b8" }}>当前项目还没有运行记录。</div>
                  ) : (
                    projectRuns.map((run) => (
                      <div key={run.id} style={{ ...cardStyle, padding: 10 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 700 }}>{run.title}</div>
                            <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                              {run.brief_payload?.topic_seed || "-"}
                            </div>
                          </div>
                          <Link
                            href={`/agent-flow/runs/${run.id}`}
                            style={{ ...secondaryButtonStyle, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                          >
                            查看运行
                          </Link>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </Section>
      </div>

      <Section title="项目列表" hint="项目是系列化运营容器，和模板、运行形成三层组织。">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...tableHeadStyle, width: 70 }}>ID</th>
                <th style={tableHeadStyle}>项目</th>
                <th style={{ ...tableHeadStyle, width: 140 }}>默认模板</th>
                <th style={{ ...tableHeadStyle, width: 120 }}>状态</th>
                <th style={{ ...tableHeadStyle, width: 100 }}>运行数</th>
                <th style={{ ...tableHeadStyle, width: 160 }}>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {projects.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ ...tableCellStyle, color: "#94a3b8" }}>
                    当前还没有项目记录。
                  </td>
                </tr>
              ) : (
                projects.map((project) => (
                  <tr
                    key={project.id}
                    onClick={() => setSelectedProjectId(String(project.id))}
                    style={{
                      cursor: "pointer",
                      background: String(project.id) === String(selectedProjectId) ? "rgba(79,70,229,.08)" : "transparent",
                    }}
                  >
                    <td style={tableCellStyle}>{project.id}</td>
                    <td style={tableCellStyle}>
                      <div style={{ fontWeight: 700 }}>{project.project_name}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{project.project_code}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{project.subject_domain || "-"}</div>
                    </td>
                    <td style={tableCellStyle}>{project.template?.template_name || "-"}</td>
                    <td style={tableCellStyle}><StatusTag status={project.status} /></td>
                    <td style={tableCellStyle}>{project.run_count || 0}</td>
                    <td style={tableCellStyle}>{formatDate(project.updated_at)}</td>
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
