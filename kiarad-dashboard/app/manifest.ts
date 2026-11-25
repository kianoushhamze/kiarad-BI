import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/", name: "کیاراد شفا اندیش", short_name: "کیاراد", lang: "fa-IR", dir: "rtl",
    description: "پنل عملیات، ویزیت و هوش تجاری کیاراد شفا اندیش",
    start_url: "/my-plan", scope: "/", display: "standalone",
    background_color: "#08070b", theme_color: "#08070b",
    icons: [
      { src: "/kiarad-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/kiarad-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
