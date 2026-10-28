import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get("status") || "";
    const groupId = searchParams.get("group_id") || "";
    const limit = searchParams.get("limit") || "20";
    const query = new URLSearchParams();
    query.set("limit", limit);
    if (status) {
      query.set("status", status);
    }
    if (groupId) {
      query.set("group_id", groupId);
    }
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/runs?${query.toString()}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取工作流运行列表失败");
  }
}

export async function POST(request) {
  try {
    const payload = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/runs`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "创建工作流运行失败");
  }
}
