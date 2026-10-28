import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const runId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/runs/${runId}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取工作流运行详情失败");
  }
}
