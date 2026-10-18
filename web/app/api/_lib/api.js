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
  const postForMeApiKey = request?.headers?.get("x-postforme-api-key");
  const nextHeaders = { ...headers };
  if (authorization) {
    nextHeaders.Authorization = authorization;
  }
  if (postForMeApiKey) {
    nextHeaders["x-postforme-api-key"] = postForMeApiKey;
  }
  return nextHeaders;
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
