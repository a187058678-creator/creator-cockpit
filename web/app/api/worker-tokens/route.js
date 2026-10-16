import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const groupId = searchParams.get("group_id") || "";
    const limit = searchParams.get("limit") || "50";
    const query = new URLSearchParams();
    query.set("limit", limit);
    if (groupId) {
      query.set("group_id", groupId);
    }
    return await proxyJson(
      `${getApiBaseUrl()}/worker-tokens?${query.toString()}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取 Worker Token 列表失败");
  }
}

export async function POST(request) {
  try {
    const body = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/worker-tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, request);
  } catch (error) {
    return handleProxyError(error, "创建 Worker Token 失败");
  }
}
