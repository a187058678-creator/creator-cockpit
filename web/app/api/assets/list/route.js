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
    const prefix = searchParams.get("prefix") || "assets";
    const limit = searchParams.get("limit") || "20";
    const response = await fetch(
      `${getApiBaseUrl()}/assets/list?prefix=${encodeURIComponent(prefix)}&limit=${encodeURIComponent(limit)}`,
      {
        cache: "no-store",
      }
    );
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { detail: error.message || "获取资产失败" },
      { status: 500 }
    );
  }
}
