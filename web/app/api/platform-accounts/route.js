import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const query = new URLSearchParams();
    const groupId = searchParams.get("group_id") || "";
    const platform = searchParams.get("platform") || "";
    const status = searchParams.get("status") || "";
    const limit = searchParams.get("limit") || "50";
    if (groupId) {
      query.set("group_id", groupId);
    }
    if (platform) {
      query.set("platform", platform);
    }
    if (status) {
      query.set("status", status);
    }
    query.set("limit", limit);
    return await proxyJson(`${getApiBaseUrl()}/platform-accounts?${query.toString()}`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "获取平台账号失败");
  }
}
