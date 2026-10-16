import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const taskId = searchParams.get("task_id") || "0";
    const workerCode = searchParams.get("worker_code") || "";
    const groupId = searchParams.get("group_id") || "";
    const limit = searchParams.get("limit") || "50";
    const query = new URLSearchParams();
    query.set("task_id", taskId);
    query.set("worker_code", workerCode);
    query.set("limit", limit);
    if (groupId) {
      query.set("group_id", groupId);
    }
    return await proxyJson(
      `${getApiBaseUrl()}/task-executions?${query.toString()}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取任务执行记录失败");
  }
}
