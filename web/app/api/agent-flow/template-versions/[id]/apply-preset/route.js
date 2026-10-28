import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const versionId = context.params.id;
    const payload = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/template-versions/${versionId}/apply-preset`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "应用模板预设失败");
  }
}
