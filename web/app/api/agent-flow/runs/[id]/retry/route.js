import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const runId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/runs/${runId}/retry`,
      { method: "POST" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "重试工作流运行失败");
  }
}
