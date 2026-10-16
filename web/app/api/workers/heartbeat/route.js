import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request) {
  try {
    const payload = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/workers/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, request);
  } catch (error) {
    return handleProxyError(error, "提交 Worker 心跳失败");
  }
}
