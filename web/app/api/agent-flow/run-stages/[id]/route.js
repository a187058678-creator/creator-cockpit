import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const stageId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/run-stages/${stageId}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取阶段详情失败");
  }
}
