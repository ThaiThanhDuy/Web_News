"""Static configuration: news sources and the fixed category taxonomy used by the AI classifier."""

SOURCES = [
    {
        "slug": "vnexpress",
        "name": "VnExpress",
        "homepage_url": "https://vnexpress.net/khoa-hoc-cong-nghe",
        "logo_url": "https://s.vnecdn.net/vnexpress/i/v20/logos/vne_logo_rss.png",
        "rss_url": "https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss",
    },
    {
        "slug": "genk",
        "name": "GenK",
        "homepage_url": "https://genk.vn",
        "logo_url": "https://www.google.com/s2/favicons?sz=64&domain=genk.vn",
        "rss_url": "https://genk.vn/rss/home.rss",
    },
    {
        "slug": "vietnamnet",
        "name": "VietnamNet",
        "homepage_url": "https://vietnamnet.vn/cong-nghe",
        "logo_url": "https://www.google.com/s2/favicons?sz=64&domain=vietnamnet.vn",
        # VietnamNet's own cong-nghe.rss feed has been stuck on the same
        # year-old items for a long time, so this isn't an RSS feed at all —
        # it's the category page itself. scraper/vietnamnet_scraper.py reads
        # the page's schema.org JSON-LD "latest articles" block instead,
        # which VietnamNet does keep genuinely up to date.
        "rss_url": "https://vietnamnet.vn/cong-nghe",
    },
    {
        "slug": "techcrunch",
        "name": "TechCrunch",
        "homepage_url": "https://techcrunch.com",
        "logo_url": "https://www.google.com/s2/favicons?sz=64&domain=techcrunch.com",
        "rss_url": "https://techcrunch.com/feed/",
    },
    {
        "slug": "wired",
        "name": "Wired",
        "homepage_url": "https://www.wired.com",
        "logo_url": "https://www.google.com/s2/favicons?sz=64&domain=wired.com",
        "rss_url": "https://www.wired.com/feed/rss",
    },
    {
        "slug": "engadget",
        "name": "Engadget",
        "homepage_url": "https://www.engadget.com",
        "logo_url": "https://www.google.com/s2/favicons?sz=64&domain=engadget.com",
        "rss_url": "https://www.engadget.com/rss.xml",
    },
    {
        "slug": "yt-vatvostudio",
        "name": "Vật Vờ Studio",
        "homepage_url": "https://www.youtube.com/@realvatvostudio",
        # Self-hosted (frontend/public/avatars/) instead of hotlinking
        # yt3.googleusercontent.com directly: that CDN turned out to be
        # unreliable — the same URL sometimes serves the real photo and
        # sometimes a tiny 307-byte placeholder icon depending on request
        # context, which showed up as broken/fallback avatars in the UI.
        "logo_url": "/avatars/yt-vatvostudio.jpg",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCEeXA5Tu7n9X5_zkOgGsyww",
    },
    {
        "slug": "yt-duyluandethuong",
        "name": "Duy Luân Dễ Thương",
        "homepage_url": "https://www.youtube.com/@duyluandethuong",
        "logo_url": "/avatars/yt-duyluandethuong.jpg",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCQ0jSGgYMLmRMeTE6UaPPXg",
    },
    {
        "slug": "yt-taixaitech",
        "name": "Tài Xài Tech",
        "homepage_url": "https://www.youtube.com/@taixaitech",
        "logo_url": "/avatars/yt-taixaitech.jpg",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiYYo7oPjA_MQ9i7-zoNfGA",
    },
    {
        "slug": "yt-thinkview",
        "name": "ThinkView",
        "homepage_url": "https://www.youtube.com/@thinkview",
        "logo_url": "/avatars/yt-thinkview.jpg",
        "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCMRCjWYwR5p2Plp_0ehIG6g",
    },
]

# Sources whose RSS entries are YouTube videos rather than articles: no page
# to scrape with trafilatura (YouTube's watch page is a JS app, not
# server-rendered text), so process_article uses the RSS description as
# content instead — see app/worker/tasks.py.
VIDEO_SOURCE_SLUGS = {"yt-vatvostudio", "yt-duyluandethuong", "yt-taixaitech", "yt-thinkview"}

# Used to pick a "winner" when the same story is covered by multiple sources
# (see app/services/clustering.py): the article from the source with the
# lowest number here is kept visible, the rest are marked as duplicates.
# Roughly reflects each outlet's global tech-journalism reach/authority.
SOURCE_PRIORITY = {
    "techcrunch": 1,
    "wired": 2,
    "engadget": 3,
    "vnexpress": 4,
    "genk": 5,
    "vietnamnet": 6,
    "yt-vatvostudio": 7,
    "yt-duyluandethuong": 8,
    "yt-taixaitech": 9,
    "yt-thinkview": 10,
}

# Fixed taxonomy the LLM must classify every article into (kept in sync with the
# `category` enum described in the AI prompt in app/services/llm.py).
CATEGORIES = [
    {"slug": "ai", "name": "Trí tuệ nhân tạo"},
    {"slug": "di-dong", "name": "Di động"},
    {"slug": "may-tinh", "name": "Máy tính"},
    {"slug": "phan-cung", "name": "Phần cứng"},
    {"slug": "phan-mem", "name": "Phần mềm"},
    {"slug": "game", "name": "Game"},
    {"slug": "startup", "name": "Startup"},
    {"slug": "mang-xa-hoi", "name": "Mạng xã hội"},
    {"slug": "an-ninh-mang", "name": "An ninh mạng"},
    {"slug": "khoa-hoc", "name": "Khoa học"},
    {"slug": "khac", "name": "Khác"},
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
