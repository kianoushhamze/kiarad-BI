export const API_URL =
  typeof window !== "undefined"
    ? window.location.origin + "/api"
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000");

export async function api<T>(path: string): Promise<T> {
  const response = await fetch(API_URL + path, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("API Error: " + String(response.status));
  }

  return response.json();
}
