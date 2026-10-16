import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request) {
  try {
    const authorization = request.headers.get("authorization") || "";
    return await proxyJson(`${getApiBaseUrl()}/auth/logout`, {
      method: "POST",
      headers: authorization ? { Authorization: authorization } : {},
    });
  } catch (error) {
    return handleProxyError(error, "退出登录失败");
  }
}
