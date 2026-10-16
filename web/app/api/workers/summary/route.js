import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const groupId = searchParams.get("group_id") || "";
    const query = new URLSearchParams();
    if (groupId) {
      query.set("group_id", groupId);
    }
    return await proxyJson(`${getApiBaseUrl()}/workers/summary${query.toString() ? `?${query.toString()}` : ""}`, {
      cache: "no-store",
    }, request);
  } catch (error) {
    return handleProxyError(error, "获取 Worker 摘要失败");
  }
}
