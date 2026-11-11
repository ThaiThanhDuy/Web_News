import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Tech Digest — Tin công nghệ tóm tắt bởi AI",
    short_name: "Tech Digest",
    description:
      "Tổng hợp tin công nghệ mới nhất từ VnExpress, GenK và VietnamNet. AI tóm tắt 3 ý chính, gắn thẳng link bài gốc.",
    lang: "vi",
    start_url: "/?source=pwa",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0a0f1c",
    theme_color: "#5b4be6",
    categories: ["news", "technology"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
