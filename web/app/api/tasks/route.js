import { getApiBaseUrl, handleProxyError, proxyJson } from "../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get("status") || "";
    const taskType = searchParams.get("task_type") || "";
    const groupId = searchParams.get("group_id") || "";
    const limit = searchParams.get("limit") || "20";
    const query = new URLSearchParams();
    query.set("status", status);
    query.set("limit", limit);
    if (taskType) {
      query.set("task_type", taskType);
    }
    if (groupId) {
      query.set("group_id", groupId);
    }
    return await proxyJson(
      `${getApiBaseUrl()}/tasks?${query.toString()}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "获取任务列表失败");
  }
}

export async function POST(request) {
  try {
    const payload = await request.json();
    return await proxyJson(`${getApiBaseUrl()}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }, request);
  } catch (error) {
    return handleProxyError(error, "创建任务失败");
  }
}
