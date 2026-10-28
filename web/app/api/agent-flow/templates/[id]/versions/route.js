import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const templateId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/templates/${templateId}/versions`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取模板版本列表失败");
  }
}
