import type { Metadata, Viewport } from "next";
import { Be_Vietnam_Pro } from "next/font/google";
import Script from "next/script";

import { AuroraBackground } from "@/components/aurora-background";
import { BackToTop } from "@/components/back-to-top";
import { Header } from "@/components/header";
import { OfflineIndicator, ServiceWorkerRegister } from "@/components/pwa";
import { getCategories } from "@/lib/api";
import "./globals.css";

const THEME_INIT_SCRIPT = `
try {
  var stored = localStorage.getItem('theme');
  var isDark = stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('dark', isDark);
} catch (e) {}
`;

const beVietnamPro = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Tech Digest — Tin công nghệ tóm tắt bởi AI",
  description:
    "Tổng hợp tin công nghệ mới nhất từ VnExpress, GenK và VietnamNet. AI tóm tắt 3 ý chính, gắn thẳng link bài gốc, cập nhật mỗi 10-15 phút.",
  applicationName: "Tech Digest",
  appleWebApp: {
    capable: true,
    title: "Tech Digest",
    statusBarStyle: "black-translucent",
  },
  formatDetection: { telephone: false },
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0f1c" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const categories = await getCategories();

  return (
    <html lang="vi" className={beVietnamPro.variable} suppressHydrationWarning>
      <head>
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
      </head>
      <body className="relative bg-grid font-sans antialiased">
        <AuroraBackground />
        <div className="relative z-10 flex min-h-screen flex-col">
          <Header categories={categories} />
          <main className="container flex-1 py-4 sm:py-8">{children}</main>
        </div>

        <BackToTop />
        <OfflineIndicator />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
