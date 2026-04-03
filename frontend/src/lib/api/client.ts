const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: Record<string, any> | FormData;
  params?: Record<string, string | number | boolean | undefined>;
}

class ApiError extends Error {
  constructor(public status: number, public detail: string, public errorCode?: string) {
    super(detail);
    this.name = "ApiError";
  }
}

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function getStoredOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("organization_id");
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, params, headers: extraHeaders, ...rest } = options;

  let url = `${API_BASE}/api/v1${path}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) searchParams.set(k, String(v));
    });
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = { ...extraHeaders as Record<string, string> };
  const token = getStoredToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const orgId = getStoredOrgId();
  if (orgId) headers["X-Organization-ID"] = orgId;

  let fetchBody: BodyInit | undefined;
  if (body instanceof FormData) {
    fetchBody = body;
  } else if (body) {
    headers["Content-Type"] = "application/json";
    fetchBody = JSON.stringify(body);
  }

  const res = await fetch(url, { ...rest, headers, body: fetchBody });

  if (!res.ok) {
    let detail = "Request failed";
    try {
      const err = await res.json();
      detail = err.detail || JSON.stringify(err);
    } catch {}
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string, params?: Record<string, any>) => request<T>(path, { method: "GET", params }),
  post: <T>(path: string, body?: Record<string, any>) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: Record<string, any>) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) => request<T>(path, { method: "POST", body: formData }),
};

export { ApiError };
