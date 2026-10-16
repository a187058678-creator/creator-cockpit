import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request, { params }) {
  try {
    return await proxyJson(`${getApiBaseUrl()}/groups/${params.id}/members`, {
      cache: "no-store",
    }, request);
  } catch (error) {
    return handleProxyError(error, "获取账号组成员失败");
  }
}

export async function POST(request, { params }) {
  try {
    const body = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/groups/${params.id}/members`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, request);
  } catch (error) {
    return handleProxyError(error, "添加账号组成员失败");
  }
}
