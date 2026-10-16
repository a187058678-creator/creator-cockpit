import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const authorization = request.headers.get("authorization") || "";
    return await proxyJson(`${getApiBaseUrl()}/auth/me`, {
      cache: "no-store",
      headers: authorization ? { Authorization: authorization } : {},
    });
  } catch (error) {
    return handleProxyError(error, "获取当前登录信息失败");
  }
}
