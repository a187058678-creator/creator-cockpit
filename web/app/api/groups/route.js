import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get("limit") || "50";
    return await proxyJson(
      `${getApiBaseUrl()}/groups?limit=${encodeURIComponent(limit)}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取账号组列表失败");
  }
}

export async function POST(request) {
  try {
    const body = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/groups`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, request);
  } catch (error) {
    return handleProxyError(error, "创建账号组失败");
  }
}
