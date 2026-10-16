import { getApiBaseUrl, handleProxyError, proxyJson } from "../../_lib/api";

export const dynamic = "force-dynamic";

export async function PATCH(request, { params }) {
  try {
    const body = await request.json();
    return await proxyJson(
      `${getApiBaseUrl()}/users/${params.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      request
    );
  } catch (error) {
    return handleProxyError(error, "更新用户失败");
  }
}
