/** @type {import('next').NextConfig} */
const nextConfig = {
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
};

export default nextConfig;
