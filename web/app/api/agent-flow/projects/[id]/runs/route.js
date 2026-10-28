import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const projectId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/projects/${projectId}/runs`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取项目运行列表失败");
  }
}
