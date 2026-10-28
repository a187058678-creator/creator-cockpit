import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const versionId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/template-versions/${versionId}/publish`,
      { method: "POST" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "切换当前模板版本失败");
  }
}
