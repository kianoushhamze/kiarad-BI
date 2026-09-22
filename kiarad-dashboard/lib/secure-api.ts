
import { API_URL } from "./api";

export type SessionUser = {
  id: number;
  username: string;
  full_name: string;
  role: "ceo" | "sales_manager" | "salesperson" | "finance";
  salesperson_id?: number | null;
};

const TOKEN_KEY = "kiarad_access_token";
const USER_KEY = "kiarad_session_user";

export function getToken() {
  return typeof window === "undefined" ? "" : localStorage.getItem(TOKEN_KEY) ?? "";
}

export function saveSession(token: string, user: SessionUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getSavedUser(): SessionUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function buildHeaders(options: RequestInit): Record<string, string> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const extra = (options.headers ?? {}) as Record<string, string>;
  const headers: Record<string, string> = Object.assign({}, extra);
  if (!isFormData) {
    Object.assign(headers, { "Content-Type": "application/json" });
  }
  const token = getToken();
  if (token) {
    Object.assign(headers, { Authorization: "Bearer " + token });
  }
  return headers;
}

export async function secureApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(API_URL + path, Object.assign({}, options, {
    headers: buildHeaders(options),
    cache: "no-store"
  }));
  if (response.status === 401) clearSession();
  if (!response.ok) {
    const body = await response.json().catch(function () { return null; });
    const detail = body && body.detail ? String(body.detail) : "خطای سرویس (" + response.status + ")";
    throw new Error(detail);
  }
  return response.json();
}

export async function authFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(API_URL + path, Object.assign({}, options, {
    headers: buildHeaders(options),
    cache: "no-store"
  }));
}
