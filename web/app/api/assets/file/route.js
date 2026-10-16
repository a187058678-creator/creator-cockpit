import { NextResponse } from "next/server";
import { getApiBaseUrl, handleProxyError, withAuthHeaders } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function POST(request) {
  try {
    const { searchParams } = new URL(request.url);
    const prefix = searchParams.get("prefix") || "assets";
    const groupId = searchParams.get("group_id") || "";
    const sourceFormData = await request.formData();
    const formData = new FormData();

    for (const [key, value] of sourceFormData.entries()) {
      formData.append(key, value);
    }

    const response = await fetch(
      `${getApiBaseUrl()}/assets/upload-file?prefix=${encodeURIComponent(prefix)}${groupId ? `&group_id=${encodeURIComponent(groupId)}` : ""}`,
      {
        method: "POST",
        body: formData,
        cache: "no-store",
        headers: withAuthHeaders(request),
      }
    );
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return handleProxyError(error, "文件上传失败");
  }
}
