// Platform credentials deliberately stay in memory, never in URLs or storage.
let token = "";

export const platformToken = () => token;

export function setPlatformToken(value: string) {
  token = value;
  window.dispatchEvent(new Event("pharma-platform-auth"));
}

export async function platformRequest<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const multipart = body instanceof FormData;
  const requestToken = token;
  const response = await fetch(applicationCenterPath(path), {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: {
      ...(multipart ? {} : { "Content-Type": "application/json" }),
      ...(requestToken ? { Authorization: requestToken } : {}),
    },
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(multipart ? 180000 : 60000),
  });
  if (response.status === 401 && requestToken && token === requestToken) setPlatformToken("");
  const data = await response.json().catch(() => {
    throw new Error(`平台返回非 JSON 响应（${response.status}）`);
  });
  if (!response.ok || (data.code !== undefined && data.code !== 0)) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.message || `平台请求失败（${response.status}）`);
  }
  return ("payload" in data ? data.payload : data) as T;
}

function applicationCenterPath(path: string): string {
  return /^\/api\/(user|wp|datasource|kb|askdata)\//.test(path)
    ? path.replace(/^\/api\//, "/api/application-center/v1/")
    : path;
}
