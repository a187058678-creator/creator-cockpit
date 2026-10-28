import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const groupId = searchParams.get("group_id") || "";
    const status = searchParams.get("status") || "";
    const limit = searchParams.get("limit") || "50";
    const query = new URLSearchParams();
    query.set("limit", limit);
    if (groupId) {
      query.set("group_id", groupId);
    }
    if (status) {
      query.set("status", status);
    }
    return await proxyJson(`${getApiBaseUrl()}/agent-flow/projects?${query.toString()}`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "获取项目列表失败");
  }
}

export async function POST(request) {
  try {
    const payload = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/projects`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "创建项目失败");
  }
}
