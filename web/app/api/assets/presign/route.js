import { NextResponse } from "next/server";
import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const key = searchParams.get("key");
    if (!key) {
      return NextResponse.json({ detail: "缺少 key 参数" }, { status: 400 });
    }
    return await proxyJson(
      `${getApiBaseUrl()}/assets/presign?key=${encodeURIComponent(key)}`,
      { cache: "no-store" },
      request
    );
  } catch (error) {
    return handleProxyError(error, "生成预签名链接失败");
  }
}
