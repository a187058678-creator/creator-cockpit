import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request, context) {
  try {
    const taskId = context.params.id;
    return await proxyJson(`${getApiBaseUrl()}/tasks/${taskId}/retry`, {
      method: "POST",
    }, request);
  } catch (error) {
    return handleProxyError(error, "重试任务失败");
  }
}
