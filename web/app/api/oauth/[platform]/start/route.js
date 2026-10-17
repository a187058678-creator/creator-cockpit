import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, { params }) {
  try {
    const resolvedParams = await params;
    const { searchParams } = new URL(request.url);
    const query = new URLSearchParams();
    const groupId = searchParams.get("group_id") || "";
    if (groupId) {
      query.set("group_id", groupId);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return await proxyJson(`${getApiBaseUrl()}/oauth/${resolvedParams.platform}/start${suffix}`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "发起 OAuth 连接失败");
  }
}
