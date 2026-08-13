import type { Metadata } from "next";
import { Be_Vietnam_Pro } from "next/font/google";
import Script from "next/script";

import { AuroraBackground } from "@/components/aurora-background";
import { BackToTop } from "@/components/back-to-top";
import { CategoryNav } from "@/components/category-nav";
import { Header } from "@/components/header";
import { SourceNav } from "@/components/source-nav";
import { getCategories, getSources } from "@/lib/api";
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
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [sources, categories] = await Promise.all([getSources(), getCategories()]);

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
          <Header />
          <div className="container flex-1 py-8">
            {/* lg:px-60 = w-52 (sidebar) + gap-8, reserving the same room the
                fixed sidebars below occupy so content never sits under them. */}
            <main className="lg:px-60">
              <div className="space-y-3 lg:hidden">
                <CategoryNav categories={categories} layout="horizontal" />
                <SourceNav sources={sources} layout="horizontal" className="mb-6" />
              </div>
              {children}
            </main>
          </div>
        </div>

        {/* Fixed (not sticky) side panels: pinned to the viewport regardless
            of scroll position, while the page underneath scrolls freely.
            Reusing the bare `container` class here — with no extra padding
            of its own — guarantees this lines up exactly with the content
            container above at every breakpoint, without hand-computed
            offsets. */}
        <div className="pointer-events-none fixed inset-0 z-20 hidden lg:block">
          <div className="container relative mx-auto h-full">
            <aside className="pointer-events-auto absolute left-4 top-24 w-52">
              <div className="glass-card max-h-[calc(100vh-8rem)] space-y-2 overflow-y-auto rounded-2xl p-3 shadow-lg shadow-black/[0.03] dark:shadow-black/20">
                <div className="px-2 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Chuyên mục
                </div>
                <CategoryNav categories={categories} layout="vertical" />
              </div>
            </aside>

            <aside className="pointer-events-auto absolute right-4 top-24 w-52">
              <div className="glass-card max-h-[calc(100vh-8rem)] space-y-2 overflow-y-auto rounded-2xl p-3 shadow-lg shadow-black/[0.03] dark:shadow-black/20">
                <div className="px-2 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Nguồn tin
                </div>
                <SourceNav sources={sources} layout="vertical" />
              </div>
            </aside>
          </div>
        </div>

        <BackToTop />
      </body>
    </html>
  );
}
