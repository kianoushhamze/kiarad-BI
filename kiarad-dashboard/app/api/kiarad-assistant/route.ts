import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_URL = "http://127.0.0.1:8000/assistant/chat";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };

    const auth = request.headers.get("authorization");

    if (auth) {
      headers.Authorization = auth;
    }

    const backendResponse = await fetch(BACKEND_URL, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
    });

    const text = await backendResponse.text();

    return new NextResponse(text, {
      status: backendResponse.status,
      headers: {
        "Content-Type":
          backendResponse.headers.get("content-type") ||
          "application/json; charset=utf-8",
      },
    });

  } catch (error) {
    console.error("Kiarad assistant proxy error:", error);

    return NextResponse.json(
      {
        detail: "ارتباط با موتور دستیار کیاراد برقرار نشد.",
      },
      {
        status: 502,
      }
    );
  }
}
