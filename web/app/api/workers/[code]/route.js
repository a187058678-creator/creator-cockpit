import { NextResponse } from "next/server";
import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function DELETE(request, { params }) {
  try {
    const workerCode = decodeURIComponent(params.code || "");
    if (!workerCode) {
      return NextResponse.json({ detail: "缺少 Worker 编号" }, { status: 400 });
    }

    return await proxyJson(
      `${getApiBaseUrl()}/workers/${encodeURIComponent(workerCode)}`,
      {
        method: "DELETE",
        cache: "no-store",
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "删除 Worker 节点失败");
  }
}
