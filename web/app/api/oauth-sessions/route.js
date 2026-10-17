import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const query = new URLSearchParams();
    const groupId = searchParams.get("group_id") || "";
    const platform = searchParams.get("platform") || "";
    const limit = searchParams.get("limit") || "20";
    if (groupId) {
      query.set("group_id", groupId);
    }
    if (platform) {
      query.set("platform", platform);
    }
    query.set("limit", limit);
    return await proxyJson(`${getApiBaseUrl()}/oauth-sessions?${query.toString()}`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "获取 OAuth 会话失败");
  }
}
