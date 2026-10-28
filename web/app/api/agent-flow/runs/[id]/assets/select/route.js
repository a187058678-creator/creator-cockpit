import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const runId = context.params.id;
    const payload = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/runs/${runId}/assets/select`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "选择主版本资产失败");
  }
}
