import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const stageId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/run-stages/${stageId}/retry`,
      { method: "POST" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "单阶段重跑失败");
  }
}
