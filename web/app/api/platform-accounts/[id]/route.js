import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function PATCH(request, { params }) {
  try {
    const resolvedParams = await params;
    const accountId = resolvedParams.id;
    const payload = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/platform-accounts/${accountId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, request);
  } catch (error) {
    return handleProxyError(error, "更新平台账号失败");
  }
}
