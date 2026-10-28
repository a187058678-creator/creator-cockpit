import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const projectId = context.params.id;
    return await proxyJson(`${getApiBaseUrl()}/agent-flow/projects/${projectId}`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "获取项目详情失败");
  }
}

export async function PUT(request, context) {
  try {
    const projectId = context.params.id;
    const payload = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/projects/${projectId}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "更新项目失败");
  }
}
