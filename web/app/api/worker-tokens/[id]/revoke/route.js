import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, { params }) {
  try {
    const body = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/worker-tokens/${params.id}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, request);
  } catch (error) {
    return handleProxyError(error, "吊销 Worker Token 失败");
  }
}
