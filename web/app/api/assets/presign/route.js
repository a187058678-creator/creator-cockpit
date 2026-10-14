import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getApiBaseUrl() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("缺少 NEXT_PUBLIC_API_BASE_URL");
  }
  return apiBaseUrl.replace(/\/+$/, "");
}

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const key = searchParams.get("key");
    if (!key) {
      return NextResponse.json({ detail: "缺少 key 参数" }, { status: 400 });
    }
    const response = await fetch(
      `${getApiBaseUrl()}/assets/presign?key=${encodeURIComponent(key)}`,
      {
        cache: "no-store",
      }
    );
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: error.message || "生成预签名链接失败" },
      { status: 500 }
    );
  }
}
