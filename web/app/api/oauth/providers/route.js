import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    return await proxyJson(`${getApiBaseUrl()}/oauth/providers`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "获取 OAuth 平台配置失败");
  }
}
