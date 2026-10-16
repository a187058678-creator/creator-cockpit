import { NextResponse } from "next/server";

export function getApiBaseUrl() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("缺少 NEXT_PUBLIC_API_BASE_URL");
  }
  return apiBaseUrl.replace(/\/+$/, "");
}

export function withAuthHeaders(request, headers = {}) {
  const authorization = request?.headers?.get("authorization");
  return authorization
    ? { ...headers, Authorization: authorization }
    : headers;
}

export async function proxyJson(url, init = {}, request) {
  const nextInit = {
    ...init,
    headers: withAuthHeaders(request, init.headers || {}),
  };
  const response = await fetch(url, nextInit);
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export function handleProxyError(error, fallbackMessage) {
  return NextResponse.json(
    { detail: error.message || fallbackMessage },
    { status: 500 }
  );
}
