
import { API_URL } from "./api";

export type SessionUser = {
  id: number;
  username: string;
  full_name: string;
  role: "ceo" | "sales_manager" | "salesperson" | "visitor" | "finance";
  salesperson_id?: number | null;
};

const TOKEN_KEY = "kiarad_access_token";
const USER_KEY = "kiarad_session_user";
let queryTokenConsumed = false;

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken() {
  if (typeof window === "undefined") return "";
  const storedToken = localStorage.getItem(TOKEN_KEY) ?? "";
  try {
    const params = new URLSearchParams(window.location.search);
    const queryToken = params.get("token");
    if (queryToken) {
      const mayImport = !queryTokenConsumed;
      queryTokenConsumed = true;
      // Remove the legacy credential from the address without losing navigation state.
      params.delete("token");
      const search = params.toString();
      try {
        window.history?.replaceState(window.history.state, "", `${window.location.pathname}${search ? "?" + search : ""}${window.location.hash}`);
      } catch {}
      if (!storedToken && mayImport) {
        localStorage.setItem(TOKEN_KEY, queryToken);
        return queryToken;
      }
    }
  } catch {}
  return storedToken;
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
  queryTokenConsumed = true;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function buildHeaders(options: RequestInit, token = getToken()): Record<string, string> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const extra = (options.headers ?? {}) as Record<string, string>;
  const headers: Record<string, string> = Object.assign({}, extra);
  if (!isFormData) {
    Object.assign(headers, { "Content-Type": "application/json" });
  }
  if (token) {
    Object.assign(headers, { Authorization: "Bearer " + token });
  }
  return headers;
}

export async function secureApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const requestToken = getToken();
  const response = await fetch(API_URL + path, Object.assign({}, options, {
    headers: buildHeaders(options, requestToken),
    cache: "no-store"
  }));
  // A late rejection for an old request must not erase a newer login.
  if (response.status === 401 && requestToken && localStorage.getItem(TOKEN_KEY) === requestToken) clearSession();
  if (!response.ok) {
    const body = await response.json().catch(function () { return null; });
    const detail = response.status === 401
      ? (getToken() ? "درخواست با نشست قبلی انجام شد؛ دوباره تلاش کنید." : "نشست شما معتبر نیست؛ دوباره وارد شوید.")
      : typeof body?.detail === "string" ? body.detail
      : Array.isArray(body?.detail) ? body.detail.map((item: {msg?: string}) => item?.msg).filter(Boolean).join("، ") || "اطلاعات درخواست معتبر نیست."
      : "خطای سرویس (" + response.status + ")";
    throw new ApiError(detail, response.status);
  }
  return response.json();
}

export async function authFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(API_URL + path, Object.assign({}, options, {
    headers: buildHeaders(options),
    cache: options.cache ?? "no-store"
  }));
}
