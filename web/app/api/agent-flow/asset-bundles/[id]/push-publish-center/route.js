import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const bundleId = context.params.id;
    return await proxyJson(
      `${getApiBaseUrl()}/agent-flow/asset-bundles/${bundleId}/push-publish-center`,
      { method: "POST" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "推送发布中心失败");
  }
}
