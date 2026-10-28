import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const assetId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/assets/${assetId}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取资产详情失败");
  }
}

export async function PUT(request, context) {
  try {
    const assetId = context.params.id;
    const payload = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/assets/${assetId}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "更新资产失败");
  }
}
