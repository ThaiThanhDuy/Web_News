# Tech Digest — Trang tin công nghệ tổng hợp bằng AI

Tự động cào tin từ **VnExpress**, **GenK**, **VietnamNet**, **TechCrunch**, **Wired** và **Engadget**,
dùng AI mở chạy tại chỗ (qua Ollama) để tóm tắt, trích từ khóa, phân loại, phân tích cảm xúc — rồi
hiển thị dưới dạng feed 1 cột kiểu mạng xã hội, cuộn vô hạn. Khi nhiều nguồn cùng đưa tin một chủ đề,
hệ thống tự động ẩn bớt, chỉ giữ lại bản từ nguồn uy tín hơn (xem mục "Lọc trùng lặp" bên dưới). Mỗi
bài luôn có nút link thẳng về bài gốc. Không có đăng nhập, like, comment, bookmark hay share — chỉ đọc.

## Kiến trúc

```text
┌─────────────┐      ┌──────────────┐      ┌───────────────────┐
│  Next.js UI │─────▶│  FastAPI     │─────▶│ PostgreSQL+pgvector│
│  (SSR/ISR)  │ REST │  (read API)  │      │  articles/sources  │
└─────────────┘      └──────────────┘      └───────────────────┘
                                                      ▲
                      ┌──────────────┐                │
                      │ Celery beat  │  every 10 min  │
                      │ + worker     │────────────────┘
                      └──────┬───────┘
                             │ 1) feedparser (RSS) / JSON-LD (VietnamNet)
                             │ 2) trafilatura (clean text)
                             │ 3) Ollama LLM (JSON: summary/keywords/category/sentiment)
                             │ 4) sentence-transformers (embedding, free, local)
                             │ 5) pgvector cosine search → cross-source clustering
                             │ 6) dedup: keep only the highest-priority source per cluster
                             │ 7) hotness score = f(freshness, cross-source reach, AI score)
                      ┌──────┴───────┐
                      │    Redis     │  (Celery broker/result backend)
                      └──────────────┘
```

- **Frontend**: Next.js (App Router) + Tailwind CSS. Server Components fetch the API with
  `next.revalidate` (ISR) — no client JS needed for the initial feed.
- **Backend**: FastAPI, read-only REST API (`/api/articles`, `/api/articles/hot`,
  `/api/articles/new-count`, `/api/categories`, `/api/sources`).
- **Database**: PostgreSQL + `pgvector` — embeddings are used to detect the same story covered by
  multiple outlets (clustering), which feeds into the hotness score.
- **Task queue**: Redis + Celery (beat schedules the scrape every 10 min, worker runs the pipeline
  per article: extract → summarize → embed → cluster → score; plus periodic hotness recompute and
  old-article cleanup).
- **AI provider**: a local open model served by [Ollama](https://ollama.com) — private, free, no
  rate limit, no API key. Speed depends entirely on this machine's CPU/GPU (see "Chạy AI tại chỗ"
  below). Embeddings also run locally via `sentence-transformers`.

All 6 RSS/scrape sources were verified working:

| Source     | Feed URL                                   |
|------------|---------------------------------------------|
| VnExpress  | `https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss` |
| GenK       | `https://genk.vn/rss/home.rss` (requires a browser User-Agent, already handled) |
| VietnamNet | `https://vietnamnet.vn/cong-nghe` (page's JSON-LD, not RSS — see below) |
| TechCrunch | `https://techcrunch.com/feed/` |
| Wired      | `https://www.wired.com/feed/rss` |
| Engadget   | `https://www.engadget.com/rss.xml` |

TechCrunch's RSS carries no thumbnail at all — the scraper falls back to the article page's
`og:image` meta tag in that case (see `scraper/content_extractor.py`).

VietnamNet's own `cong-nghe.rss` feed has been stuck returning the same year-old items for a long
time (not actually refreshed), so `scraper/vietnamnet_scraper.py` reads the category page's
schema.org JSON-LD "latest articles" block instead, which VietnamNet does keep current.

## Lọc trùng lặp (dedup)

Khi nhiều nguồn cùng đưa tin về một sự kiện (ví dụ TechCrunch, Wired và VnExpress cùng viết về một
sản phẩm mới ra mắt), pgvector sẽ gom các bài đó vào chung một `ArticleCluster` dựa trên độ tương đồng
embedding (đa ngôn ngữ, nên khớp được cả tiếng Việt với tiếng Anh). Thay vì hiển thị tất cả, hệ thống
chỉ giữ lại **một** bài — từ nguồn có độ ưu tiên cao nhất — các bài còn lại bị đánh dấu
`is_duplicate=True` và bị loại khỏi mọi API/feed.

Thứ tự ưu tiên (`SOURCE_PRIORITY` trong `app/constants.py`, số nhỏ hơn = ưu tiên hơn):

```text
1. TechCrunch   3. Engadget    5. GenK
2. Wired        4. VnExpress   6. VietnamNet
```

Bài "thắng" trong cụm vẫn hiển thị badge "N nguồn cùng đưa tin" (dựa trên `cluster.source_count`,
đếm mọi nguồn kể cả các bản bị ẩn) — đây cũng là một tín hiệu đầu vào của thuật toán Tin Nổi Bật.
Muốn đổi thứ tự ưu tiên, sửa `SOURCE_PRIORITY` rồi chạy lại
`python scripts/migrate_dedup_and_sources.py` để backfill lại các cụm đã có.

Muốn bỏ hẳn một nguồn (xoá nguồn + toàn bộ bài đã cào từ nguồn đó)? Xoá entry khỏi `SOURCES` trong
`app/constants.py` rồi chạy `python scripts/remove_source.py <slug>`.

## Yêu cầu hệ thống

- Python 3.11+ (máy này có 3.12.3 ✓)
- Node.js 18.17+ (máy này có 18.19.1 ✓)
- PostgreSQL 14+ với extension `pgvector`
- Redis 6+
- Không cần API key nào — AI chạy tại chỗ qua Ollama (xem bước cài đặt bên dưới). Cần khoảng 5GB
  dung lượng trống cho model.

## Cài đặt nhanh (1 lệnh)

Sau khi có PostgreSQL + Redis đang chạy (bước 1 bên dưới), lệnh này cài hết phần còn lại — venv +
thư viện Python, thư viện Node, và Ollama (tải binary + model AI):

```bash
./setup.sh
```

An toàn để chạy lại nhiều lần (bỏ qua mọi bước đã làm rồi). Sau đó vẫn cần `python scripts/init_db.py`
(lần đầu, xem bước 3) rồi mới `./start-dev.sh` được. Các mục 1-4 bên dưới là chi tiết từng phần việc
`setup.sh` làm giúp, để tham khảo hoặc chạy tay riêng lẻ khi cần.

## 1. Cài đặt PostgreSQL + pgvector và Redis (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgresql-16-pgvector redis-server

sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server
```

Tạo user + database:

```bash
sudo -u postgres psql -c "CREATE USER web_news WITH PASSWORD 'web_news';"
sudo -u postgres psql -c "CREATE DATABASE web_news OWNER web_news;"
sudo -u postgres psql -d web_news -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

> Ghi chú: script `backend/scripts/init_db.py` cũng tự chạy `CREATE EXTENSION IF NOT EXISTS vector`,
> nhưng chạy sẵn bằng user `postgres` ở trên để chắc chắn có quyền, phòng khi extension chưa được
> đánh dấu "trusted" trên máy bạn.

Kiểm tra Redis đang chạy: `redis-cli ping` → phải trả về `PONG`.

## 2. Cài đặt AI tại chỗ (Ollama)

Không cần API key, không giới hạn tốc độ, dữ liệu không rời khỏi máy.

```bash
./setup-ollama.sh   # chạy 1 lần: tự tải Ollama (bản portable, không cần root) + tải model
```

Script này tải model `qwen2.5:14b-instruct` (mặc định trong `backend/.env.example`, ~9GB) — chọn
lớn hơn 7b/3b vì chất lượng tiếng Việt và khả năng phân loại/tóm tắt tốt hơn rõ rệt, hỗ trợ JSON mode
ổn định. An toàn chạy lại (bỏ qua nếu đã cài/đã tải rồi).

**Đánh đổi cần biết**: chạy CPU-only (không có GPU rời), một bài viết mất khoảng **vài phút** để
phân tích đầy đủ với model 14b (chậm hơn đáng kể so với 7b, đổi lại chất lượng tốt hơn). `start-dev.sh`
mặc định chỉ chạy 2 worker Celery song song (khớp với `OLLAMA_NUM_PARALLEL=2` trong `start-ollama.sh`)
— đã thử tăng lên 4 trên máy 8 nhân và đo được là **chậm hơn**: các request tranh nhau cùng vài lõi
CPU khiến mỗi bài chậm đi đáng kể, một số bài còn timeout rồi phải retry. Nếu có GPU tốt, tăng lại
bằng biến `CELERY_CONCURRENCY=8 OLLAMA_NUM_PARALLEL=8 ./start-dev.sh` (chỉnh cả hai cùng lúc) và đo
lại thực tế thay vì tăng mù. Muốn nhanh hơn (đánh đổi chất lượng), đổi `OLLAMA_MODEL` trong
`backend/.env` sang `qwen2.5:7b-instruct` hoặc `qwen2.5:3b-instruct` rồi `ollama pull <model>`.

Việc tự fine-tune model riêng (dùng dữ liệu bài viết đã có để huấn luyện tiếp) chưa được làm ở đây —
để ngỏ cho sau này khi có phần cứng GPU và bộ dữ liệu phù hợp.

## 3. Cài đặt Backend

`./setup.sh` (hoặc `./setup-ollama.sh` một mình) đã lo phần venv + pip install + copy `.env` — làm
tay nếu muốn:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Sửa DATABASE_URL / REDIS_URL / OLLAMA_MODEL nếu bạn đổi khác mặc định

python scripts/init_db.py   # tạo bảng + seed nguồn tin (báo + YouTube) + danh mục — chạy 1 lần
```

> Đã cài đặt từ trước khi có dedup / nhiều nguồn? Chạy thêm
> `python scripts/migrate_dedup_and_sources.py` — script này thêm các cột còn thiếu, seed nguồn
> mới, và backfill lại các cụm bài trùng đã có sẵn. An toàn để chạy lại nhiều lần.

Kiểm tra nhanh (không cần Celery/Redis, nhưng cần Ollama đã chạy) — cào + xử lý AI ngay 1 lần, đồng bộ:

```bash
python scripts/run_scrape_once.py
```

## 4. Cài đặt Frontend

`./setup.sh` đã lo phần này rồi — làm tay nếu muốn:

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 5. Chạy toàn bộ hệ thống

Cách nhanh nhất — script tự khởi động Ollama rồi chạy cả 4 tiến trình (FastAPI, Celery worker,
Celery beat, Next.js dev) cùng lúc, Ctrl+C để dừng tất cả:

```bash
./start-dev.sh
```

Hoặc chạy tay từng service trong các terminal riêng (hữu ích khi cần xem log riêng từng phần):

```bash
# Terminal 0 — Ollama (chạy 1 lần, để nền)
./start-ollama.sh

# Terminal 1 — API
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Celery worker (xử lý AI pipeline cho từng bài)
cd backend && source venv/bin/activate
celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

# Terminal 3 — Celery beat (lên lịch cào tin mỗi 10 phút)
cd backend && source venv/bin/activate
celery -A app.worker.celery_app beat --loglevel=info

# Terminal 4 — Frontend
cd frontend && npm run dev
```

Mở http://localhost:3000. Trang sẽ trống cho tới khi Celery chạy xong lượt cào đầu tiên (hoặc bạn
đã chạy `run_scrape_once.py` ở bước 3) — feed sẽ tự làm mới nhờ ISR (`revalidate` 120s), và trang
cũng tự hiện nút "N bài viết mới" khi có bài mới được xử lý xong.

Production build của frontend: `npm run build && npm run start`.

## Cấu trúc thư mục

```text
backend/
  app/
    main.py                FastAPI app (CORS, router, tạo bảng + seed lúc khởi động)
    config.py               Đọc biến môi trường (.env)
    models.py                SQLAlchemy models (Article, Source, Category, ArticleCluster)
    schemas.py                Pydantic response schemas
    constants.py               6 nguồn tin + SOURCE_PRIORITY (dedup) + 10 danh mục cố định
    routers/                    /api/articles (?sort=feed|latest|hot), /api/articles/new-count,
                                  /api/articles/hot, /api/categories, /api/sources
    scraper/
      rss_fetcher.py             feedparser + chuẩn hoá ngày giờ + trích thumbnail
      content_extractor.py        trafilatura + og:image fallback — văn bản sạch + ảnh từ trang gốc
      vietnamnet_scraper.py        Đọc JSON-LD trên trang cong-nghe (RSS của VietnamNet bị đứng)
    services/
      llm.py                       Gọi Ollama, ép JSON schema, validate output
      embeddings.py                  sentence-transformers (multilingual, free, local)
      clustering.py                   pgvector cosine distance → gom cụm + chọn bài không trùng
      hotness.py                       Công thức tính điểm hot
    worker/
      celery_app.py                     Celery app + lịch beat (cào/tính hot/dọn tin cũ)
      tasks.py                            scrape_all_sources / process_article / recompute_hotness_scores /
                                            cleanup_old_articles
  scripts/
    init_db.py                            Tạo extension + bảng + seed (chạy 1 lần, cài đặt lần đầu)
    migrate_dedup_and_sources.py           Migration: thêm cột dedup, seed nguồn mới, backfill cụm cũ
    remove_source.py                       Xoá hẳn 1 nguồn + toàn bộ bài của nguồn đó
    run_scrape_once.py                     Cào + xử lý AI đồng bộ, không cần Celery/Redis — để test
    reclassify_categories.py               Phân loại lại category cho bài đã có (gọi AI rẻ hơn)
    reprocess_pending.py                   Xử lý lại các bài lỡ bị lỗi AI

frontend/
  app/
    layout.tsx                  Layout 3 cột: Chuyên mục (trái) — feed (giữa) — Nguồn tin (phải)
    page.tsx                    Trang chủ: feed 1 cột (5 bài hot 48h + mới nhất), cuộn vô hạn
    category/[slug]/page.tsx      Feed lọc theo chuyên mục
    source/[slug]/page.tsx          Feed lọc theo nguồn tin
  components/
    feed.tsx                       Feed: cuộn vô hạn + banner "N bài viết mới" kiểu Facebook
    feed-post.tsx                    1 bài trong feed: avatar nguồn, tóm tắt AI, ảnh, nút "Đọc bài gốc"
    category-nav.tsx, source-nav.tsx  Panel dọc (desktop) / hàng ngang (mobile) lọc chuyên mục/nguồn
    reveal.tsx, aurora-background.tsx   Hiệu ứng scroll-reveal + nền gradient động
  lib/
    api.ts                       Gọi FastAPI, có fallback an toàn nếu backend chưa chạy
    category-meta.ts               Icon + màu riêng cho từng chuyên mục

setup.sh           Cài 1 lần: venv + pip, npm install, .env files, gọi setup-ollama.sh — chạy trước start-dev.sh lần đầu
setup-ollama.sh    Cài 1 lần: tải Ollama (portable) + pull model — không khởi động server
start-ollama.sh    Khởi động Ollama server + giám sát trực tiếp ([LOG]/[SYS]/...); Ctrl+C dừng cả server
start-dev.sh       Khởi động backend + celery + frontend (không đụng Ollama, chỉ kiểm tra nó đã chạy), tự dọn tiến trình cũ trước khi chạy
```

## Thuật toán Tin Nổi Bật

```text
hotness = 100 × (0.45 × freshness + 0.30 × cross_source_reach + 0.25 × ai_hotness_score)
```

- `freshness`: suy giảm theo hàm mũ, half-life 12 giờ kể từ `published_at`.
- `cross_source_reach`: tỉ lệ số nguồn (trên tổng số nguồn đang theo dõi) cùng đưa tin về một chủ
  đề — xác định bằng cách gom cụm các bài có embedding gần nhau (cosine distance < 0.25) trong
  vòng 48 giờ, dùng pgvector.
- `ai_hotness_score`: điểm 0-100 do LLM tự đánh giá mức độ đáng chú ý của tin.

Celery beat tính lại `hotness_score` mỗi 5 phút cho các bài trong 72 giờ gần nhất (vì `freshness`
giảm dần theo thời gian dù nội dung khác không đổi). Bài cũ hơn 3 ngày (`ARTICLE_RETENTION_DAYS`) bị
xoá hẳn khỏi database mỗi giờ bởi task `cleanup_old_articles`.

## Troubleshooting

- **`psycopg2` lỗi kết nối**: kiểm tra `DATABASE_URL` trong `backend/.env`, và Postgres đang chạy
  (`sudo systemctl status postgresql`).
- **Celery không kết nối được Redis**: `redis-cli ping` phải trả `PONG`; kiểm tra `REDIS_URL`.
- **Bài không xử lý được / worker báo lỗi kết nối tới Ollama**: kiểm tra `./start-ollama.sh` đã chạy
  chưa (`curl http://localhost:11434/api/version` phải trả về JSON).
- **Xử lý chậm**: bình thường trên máy không có GPU rời — mỗi bài mất khoảng 30-60 giây với model
  mặc định. Muốn nhanh hơn: đổi sang model nhỏ hơn (`OLLAMA_MODEL=qwen2.5:3b-instruct` trong
  `backend/.env`, rồi `ollama pull qwen2.5:3b-instruct`).
- **Trang chủ trống**: bình thường nếu Celery beat/worker chưa chạy lượt đầu — chạy
  `python scripts/run_scrape_once.py` để có dữ liệu ngay, hoặc đợi tối đa 10 phút nếu đã bật
  `start-dev.sh`.
- **GenK trả 503**: do trang chặn request thiếu User-Agent — đã xử lý sẵn trong
  `scraper/rss_fetcher.py`, không cần sửa gì thêm.
- Model embedding (`sentence-transformers`) tự tải (~470MB) từ Hugging Face lần đầu chạy — cần
  mạng, chỉ tải 1 lần rồi cache lại.
