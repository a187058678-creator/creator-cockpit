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
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/summary${query.toString() ? `?${query.toString()}` : ""}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取工作流摘要失败");
  }
}
