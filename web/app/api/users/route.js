import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get("limit") || "50";
    return await proxyJson(
      `${getApiBaseUrl()}/users?limit=${encodeURIComponent(limit)}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取用户列表失败");
  }
}

export async function POST(request) {
  try {
    const body = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, request);
  } catch (error) {
    return handleProxyError(error, "创建用户失败");
  }
}
