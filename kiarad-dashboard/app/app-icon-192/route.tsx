import { ImageResponse } from "next/og";
export const dynamic = "force-static";
export function GET() {
  return new ImageResponse(<div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#6d28d9", color: "white", fontSize: 116, fontWeight: 700 }}>K</div>, { width: 192, height: 192 });
}
