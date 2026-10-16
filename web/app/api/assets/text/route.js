import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request) {
  try {
    const body = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/assets/upload-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    }, request);
  } catch (error) {
    return handleProxyError(error, "文本上传失败");
  }
}
