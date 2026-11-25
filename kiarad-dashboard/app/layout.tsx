import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kiarad BI",
  description: "سامانه هوش تجاری و داشبورد مدیریتی کیاراد",
  appleWebApp: { capable: true, title: "کیاراد", statusBarStyle: "default" },
  icons: { apple: [{ url: "/kiarad-apple-touch-icon.png", sizes: "180x180", type: "image/png" }] },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#08070b" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fa-IR" dir="rtl" className="h-full antialiased">
      <body className="min-h-full flex flex-col">

        

        {children}</body>
    </html>
  );
}



