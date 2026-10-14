import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getApiBaseUrl() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("缺少 NEXT_PUBLIC_API_BASE_URL");
  }
  return apiBaseUrl.replace(/\/+$/, "");
}

export async function PATCH(request, context) {
  try {
    const payload = await request.json();
    const taskId = context.params.id;
    const response = await fetch(`${getApiBaseUrl()}/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: error.message || "更新任务失败" },
      { status: 500 }
    );
  }
}
