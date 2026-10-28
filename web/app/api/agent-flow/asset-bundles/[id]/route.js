import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, context) {
  try {
    const bundleId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/asset-bundles/${bundleId}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取资产包详情失败");
  }
}
