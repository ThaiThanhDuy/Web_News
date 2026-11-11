/** @type {import('next').NextConfig} */
const nextConfig = {
  // Lets a verification build go to a separate folder (NEXT_DIST_DIR=.next-check
  // npm run build) without clobbering the .next of a running `next dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  images: {
    // Thumbnails come from RSS feeds / og:image of the scraped sources, whose
    // CDN subdomains vary and can change at any time. next/image throws a
    // hard render error for any unlisted hostname (this has taken the whole
    // page down twice already as sources were added), so instead of
    // maintaining a per-source allowlist that breaks on every CDN change, we
    // trust these URLs the same way plain <img> would: they only ever come
    // from the hardcoded, vetted source list in app/constants.py, never from
    // arbitrary user input.
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
  async headers() {
    return [
      {
        // The service worker must never be served stale from the HTTP cache,
        // otherwise users would be stuck on an old SW after a deploy.
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
