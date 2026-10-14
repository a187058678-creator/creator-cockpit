import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getApiBaseUrl() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("缺少 NEXT_PUBLIC_API_BASE_URL");
  }
  return apiBaseUrl.replace(/\/+$/, "");
}

export async function POST(request) {
  try {
    const body = await request.json();
    const response = await fetch(`${getApiBaseUrl()}/assets/upload-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: error.message || "文本上传失败" },
      { status: 500 }
    );
  }
}
