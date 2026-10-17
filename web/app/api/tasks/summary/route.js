import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const groupId = searchParams.get("group_id") || "";
    const taskType = searchParams.get("task_type") || "";
    const query = new URLSearchParams();
    if (groupId) {
      query.set("group_id", groupId);
    }
    if (taskType) {
      query.set("task_type", taskType);
    }
    return await proxyJson(`${getApiBaseUrl()}/tasks/summary${query.toString() ? `?${query.toString()}` : ""}`, {
      cache: "no-store",
    }, request);
  } catch (error) {
    return handleProxyError(error, "获取任务摘要失败");
  }
}
