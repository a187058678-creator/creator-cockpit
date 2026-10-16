import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function PATCH(request, context) {
  try {
    const payload = await request.json();
    const taskId = context.params.id;
    return await proxyJson(`${getApiBaseUrl()}/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, request);
  } catch (error) {
    return handleProxyError(error, "更新任务失败");
  }
}
