import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const runId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/runs/${runId}/stages`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取阶段列表失败");
  }
}
