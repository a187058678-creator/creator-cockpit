import { getApiBaseUrl, handleProxyError, proxyJson } from "../../../_lib/api";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    return await proxyJson(`${getApiBaseUrl()}/agent-flow/settings/presets`, { cache: "no-store" }, request);
  } catch (error) {
    return handleProxyError(error, "获取设置中心预设失败");
  }
}
