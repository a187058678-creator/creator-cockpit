import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request) {
  try {
    const payload = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/postforme/social-posts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, request);
  } catch (error) {
    return handleProxyError(error, "创建 Post for Me 发布失败");
  }
}
