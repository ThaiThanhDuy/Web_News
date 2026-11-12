# Tech Digest — Trang tin công nghệ tổng hợp bằng AI

Tự động cào tin từ **VnExpress**, **GenK**, **VietnamNet**, **TechCrunch**, **Wired** và
một số kênh YouTube công nghệ. AI (Groq: `gpt-oss-20b` phân loại, `gpt-oss-120b` tóm tắt) tạo 3 ý chính bằng tiếng Việt.
Kết quả hiển thị dưới dạng feed 1 cột, cuộn vô hạn. Tin trùng giữa các nguồn được gộp lại, chỉ giữ bản
từ nguồn uy tín hơn. Mỗi bài có link thẳng về bài gốc. Web là PWA: cài được lên điện thoại, đọc lại tin
đã xem khi offline, và nhận thông báo đẩy (Web Push) theo chuyên mục.

## Kiến trúc

```text
 Next.js PWA ──REST──▶ FastAPI ──▶ PostgreSQL + pgvector ◀── worker (python -m app.worker)
 (feed, SW, push)       (đọc)       items, enrichments,         │  scheduler (1 leader / advisory lock)
                                    jobs (pool việc), ...       │  7 queue, mỗi queue N luồng
                                                                ▼
                                       Redis: hạn mức token Groq, giãn cách theo tên miền, robots.txt
```

Mọi việc nền nằm trong **một pool chung là bảng `jobs`** của Postgres, chia theo 7 queue. Worker tự lấy
việc khi rảnh bằng `FOR UPDATE SKIP LOCKED` kèm lease, nên thêm worker (thêm luồng hoặc thêm máy) không
cần sửa code. Kết quả của một bước, việc đánh dấu `done` và job của bước sau được ghi **trong cùng
một transaction**, nên không có chuyện lưu dữ liệu xong mà mất job.

| Queue | Job | Việc |
| --- | --- | --- |
| `fetch` | `fetch.source`, `fetch.item` | Connector lấy item mới; tải trang bài, tách nội dung chính, lưu dữ liệu thô `.json.gz` |
| `parse` | `parse.item` | Chuẩn hóa, nhận diện ngôn ngữ, chống trùng chính xác (SHA-256) |
| `filter` | `filter.item` | Lọc rule, chống gần trùng (SimHash), embedding + gom cụm cùng sự kiện |
| `ai_fast` | `ai.classify` | `gpt-oss-20b`: chuyên mục, độ liên quan, sắc thái |
| `ai_deep` | `ai.summarize` | `gpt-oss-120b`: 3 ý chính, câu tóm tắt, từ khóa |
| `deliver` | `deliver.fanout`, `deliver.send` | Web Push theo chuyên mục đã đăng ký |
| `maintenance` | `maint.*` | Trả job hết lease, tính lại điểm hot, xóa dữ liệu hết hạn, reconcile |

Vòng đời một item: `discovered → fetched → parsed → ready → classified → enriched`, hoặc dừng ở
`filtered` / `duplicate` / `failed`. Mỗi trạng thái chưa kết thúc có đúng một job tiếp theo
(`app/pipeline/steps.py`); job `maint.reconcile` tự tạo lại job cho item nào bị kẹt.

### Thu thập dữ liệu (connector)

Mỗi loại nguồn là một connector cùng interface (`validate` / `fetch` / `health`, xem
`app/connectors/`). Connector chỉ lấy và chuẩn hóa, không gọi AI, không ghi DB. Cursor của nguồn
(`ETag`, `Last-Modified`) chỉ được cập nhật sau khi item của lần chạy đã ghi thành công.

| Nguồn | Connector | Ghi chú |
| --- | --- | --- |
| VnExpress, GenK, TechCrunch, Wired | `rss` | GenK cần User-Agent kiểu trình duyệt (đã xử lý) |
| Kinh tế trong nước: VnExpress Kinh doanh, Thanh Niên Kinh tế, Dân trí Kinh doanh, VnEconomy, CafeF | `rss` | `default_topic: kinh-te` — bỏ qua bước AI phân loại |
| Kinh tế quốc tế: CNBC, The Guardian Business, NYT Business, BBC Business, MarketWatch | `rss` | Như trên. `robots.txt` của MarketWatch cấm tải trang bài → chỉ tóm tắt từ mô tả trong feed |
| VietnamNet | `vietnamnet_jsonld` | RSS của VietnamNet bị đứng; đọc JSON-LD `ItemList` trên trang chuyên mục |
| Kênh YouTube | `youtube_api` | `robots.txt` của YouTube cấm `/feeds/videos.xml`, nên dùng YouTube Data API (cần `YOUTUBE_API_KEY`, 1 đơn vị quota mỗi lần) |

- Kiểm tra `robots.txt` trước mỗi request (cache 24 giờ trong Redis).
- Mỗi tên miền chỉ nhận 1 request mỗi `CRAWL_DOMAIN_INTERVAL_SECONDS`, tính chung cho mọi worker.
- Gặp đăng nhập, CAPTCHA, 403/429 thì dừng, không tìm cách vượt qua.
- Mỗi nguồn có lịch riêng (`fetch_interval_minutes` trong `app/constants.py`). Lỗi thì lùi lịch theo
  hàm mũ; lỗi 5 lần liên tiếp thì tạm dừng nguồn `SOURCE_PAUSE_HOURS` giờ.
- Email và số điện thoại bị che (`[email]`, `[sđt]`) trước khi lưu và trước khi gửi sang AI.

### AI và hạn mức Groq

Phân loại dùng `openai/gpt-oss-20b`, tóm tắt dùng `openai/gpt-oss-120b`, đều với JSON Schema `strict` và
`reasoning_effort=low`. Mỗi kết quả được lưu vào `enrichments`, gắn với một `pipeline_versions` ghi rõ prompt,
schema, provider và model đã tạo ra nó. Có thể chọn model tóm tắt riêng cho từng chuyên mục bằng
`SUMMARIZE_MODEL_BY_TOPIC`.

Worker tự giữ hạn mức trước khi gọi Groq (token bucket theo phút + trần theo ngày, trong Redis, **tính riêng
cho từng model**). Khi hết hạn mức, job được **hẹn lại chứ không bị tính là lỗi**, và luồng của queue đó tạm
nghỉ. Không bài nào bị bỏ vì hết hạn mức; bài mới nhất được xử lý trước.

Đo thực tế: phân loại ≈ 1.750 token/bài, tóm tắt ≈ 1.500 token/bài. Vì hạn mức Groq tính theo model, tách
hai bước sang hai model cho mỗi bước một ngân sách riêng: với trần `GROQ_DAILY_TOKEN_CAP=160000`, khoảng
**90 bài/ngày** được xử lý đầy đủ (dùng chung một model chỉ khoảng 50). Nếu đặt hai bước cùng một model, bước
phân loại tự nhường khi có bài chờ tóm tắt, để bài đã bắt đầu được xử lý xong trước. Muốn nhiều hơn: Groq
trả phí, hoặc đặt `AI_MIN_RELEVANCE` để bỏ tóm tắt tin ít quan trọng.

**Nguồn một lĩnh vực:** nguồn có `default_topic` trong `app/constants.py` (các trang kinh tế) gán thẳng lĩnh vực
cho mọi tin, **bỏ qua bước AI phân loại** (tiết kiệm khoảng 1.000–1.750 token/tin). Độ liên quan và sắc thái lấy từ
bước tóm tắt (schema tóm tắt trả thêm hai trường này).

**Tiết kiệm token (phần chạy bằng CPU, không gọi AI):**
- `services/compress.py`: trước khi gửi cho AI, nội dung bài được làm sạch (bỏ link, "Xem thêm", chú thích ảnh,
  hashtag, mốc thời gian/link tài trợ trong mô tả YouTube) và rút gọn (giữ phần mở đầu và các câu sát tiêu đề nhất)
  xuống `SUMMARIZE_MAX_CONTENT_CHARS` (2.400) / `CLASSIFY_MAX_CONTENT_CHARS` (1.200) ký tự. Trung bình ít hơn
  khoảng 31% ký tự cho bước tóm tắt.
- `services/local_classifier.py`: phân loại chuyên mục bằng kNN trên embedding, học từ nhãn AI đã gắn. **Tự kiểm
  định** mỗi 6 giờ (đánh giá bỏ-ra-một) và chỉ được dùng khi quyết định giữ/bỏ đúng ≥ 95%; tin không chắc chắn
  vẫn hỏi AI. Trạng thái xem ở dashboard.
- `AI_MAX_ITEM_AGE_HOURS` (72): tin quá cũ khi tới lượt AI bị lọc, không tốn token.
- Đổi prompt phân loại xong, chạy `python scripts/eval_classify.py` để so sánh A/B với nhãn cũ.

**Nhiều chuyên mục cho một tin:** bước tóm tắt trả thêm `related_topics` (0–3 chuyên mục bài cũng nói tới rõ ràng,
gần như không tốn thêm token). Bảng `topic_items` lưu chuyên mục chính + chuyên mục phụ; trang chuyên mục liệt kê mọi
tin gắn với nó. Ví dụ tin kinh tế về một startup AI gọi vốn hiện ở cả Kinh tế, AI và Startup; thẻ bài ghi "Cũng
thuộc: …". Thông báo đẩy cũng khớp theo chuyên mục phụ.

**Chỉ theo dõi một số lĩnh vực:** `FOLLOWED_TOPICS` (mặc định `ai,startup,phan-mem,phan-cung,kinh-te`). Tin được AI phân loại
vào lĩnh vực khác bị đánh dấu `filtered` ngay sau bước phân loại, **không tốn token tóm tắt**, và thanh chuyên mục
chỉ hiện các lĩnh vực được theo dõi. Sau khi đổi giá trị, chạy `python scripts/apply_followed_topics.py` để áp
dụng cho tin đã có trong DB.

**Model dự phòng:** `GROQ_FALLBACK_MODELS` (mặc định `qwen/qwen3.8-27b`). Khi model của một bước hết hạn mức
phút hoặc ngày, bước đó tự chuyển sang model dự phòng (cũng có hạn mức riêng), nên thêm được khoảng 100 bài/ngày
nữa. qwen chạy với `reasoning_effort=none` (`LLM_REASONING_EFFORT_BY_MODEL`). Mỗi enrichment ghi lại model đã
thực sự xử lý, xem được ở bảng `pipeline_versions`.

`LLM_PROVIDER=ollama` vẫn được giữ làm hướng mở rộng (chạy model tại chỗ qua `./start-ollama.sh`),
cùng interface provider trong `app/ai/providers.py`.

### Lọc trùng lặp

1. **Trùng chính xác:** SHA-256 của văn bản đã chuẩn hóa.
2. **Gần trùng:** SimHash 64 bit, khoảng cách Hamming ≤ `SIMHASH_MAX_DISTANCE` trong 48 giờ.
3. **Cùng sự kiện:** embedding đa ngôn ngữ (khớp được tiếng Việt với tiếng Anh) + pgvector, gom vào
   `item_clusters`. Mỗi cụm chỉ hiện **một** bài: trong các bài đã xử lý xong, bài từ nguồn có
   `priority` nhỏ nhất (TechCrunch 1 → Wired → VnExpress → GenK → VietnamNet → YouTube).
   Bài cùng sự kiện từ nguồn kém ưu tiên hơn không tốn token AI.

Embedding cần khoảng 0,5–1 GB RAM. Trên VPS nhỏ đặt `EMBEDDINGS_ENABLED=false`; bước 1 và 2 vẫn chạy.

### Điểm Tin Nổi Bật

```text
S = 100 · Σ wᵢ·xᵢ / Σ wᵢ   (chỉ trên các thành phần đang có dữ liệu)

R  độ liên quan AI chấm (0–100)                         0.25
F  độ mới e^(−λΔt), λ = ln2 / 12h                       0.30
T  độ tin cậy nguồn (sources.trust)                     0.10
C  số nguồn cùng đưa tin, log(1+C)/log(1+5)             0.10
K  keyword đang lên: mức "nóng" của keyword nóng nhất   0.15
E  tương tác: lượt mở so với kỳ vọng theo vị trí, và/hoặc
   lượt xem/giờ của video YouTube (0,5 = bình thường)   0.10
```

Job `maint.hotness` tính lại mỗi 5 phút (`app/services/hotness.py`, `ranking.py`). Bài cũ hơn
`ARTICLE_RETENTION_DAYS` (14) ngày bị xóa; dữ liệu thô sau `RAW_RETENTION_DAYS` (7) ngày.

**K — keyword đang lên** (`services/trends.py`, job `maint.trends` mỗi 10 phút): `keyword_daily` đếm mỗi keyword
xuất hiện trong bao nhiêu tin, từ bao nhiêu nguồn, mỗi ngày, giữ `KEYWORD_STATS_RETENTION_DAYS` (180) ngày, lâu hơn
bản thân tin. Mức nóng so số lần nhắc trong 24 giờ với mức nền 28 ngày; keyword phải được nhắc nhiều lần, từ hơn
một nguồn, mới "nóng".

**E — tương tác** (`services/engagement.py`, `POST /api/events`): trình duyệt gửi ẩn danh lượt hiển thị (≥ 50% thẻ
bài trên màn hình trong 0,8 giây), lượt mở bài, bấm hashtag, mở thông báo và từ khóa tìm kiếm. Server chỉ lưu
**số đếm** theo tin/giờ, theo vị trí trên feed và theo từ khóa/ngày: không lưu định danh hay IP (IP chỉ dùng tạm
để giới hạn tần suất). Trình duyệt bật Do Not Track không gửi gì. Lượt mở được so với số lượt mở *kỳ vọng* ở
những vị trí bài đã hiện, để bài đứng đầu không tự được lợi. E chỉ vào công thức khi trang có từ
`ENGAGEMENT_MIN_DAILY_IMPRESSIONS` (300) lượt hiển thị/ngày; video YouTube có thêm lượt xem công khai (job
`maint.youtube_stats`, 30 phút).

**Cá nhân hóa** (`frontend/lib/interests.ts`): hồ sơ sở thích (chuyên mục, hashtag hay đọc; giảm dần với nửa đời
14 ngày) chỉ nằm trong trình duyệt. Feed gửi kèm hồ sơ để server xếp lại phần tin nổi bật (điểm hot × (1 + mức
hợp gu)) và đánh dấu "Hợp gu bạn"; server không lưu hồ sơ. Bật/tắt và xóa trong Cài đặt.

Dashboard (`/dashboard`) có thêm: keyword đang lên, tương tác 24 giờ, tìm kiếm nhiều nhất 7 ngày.

### PWA và Web Push

- `app/manifest.ts` + `public/sw.js`: cài được lên màn hình chính; trang và API được cache theo kiểu
  network-first nên vẫn đọc được tin đã xem khi mất mạng. `/api/push/*` không bao giờ bị cache.
- Nút chuông trên header: bật thông báo, chọn chuyên mục, gửi thử, tắt. Chỉ tin có độ liên quan ≥
  `PUSH_MIN_RELEVANCE`, đăng trong `PUSH_MAX_ITEM_AGE_HOURS` giờ, tối đa `PUSH_MAX_PER_HOUR` tin/giờ.
- Bảng `deliveries` được ghi trước khi gửi và là duy nhất theo (subscription, item, kênh), nên chạy lại
  job không gửi trùng. Subscription trả về 404/410 bị xóa tự động.
- iOS không có lời nhắc cài tự động và chỉ nhận push sau khi cài vào Màn hình chính (iOS 16.4+): app
  hiện màn hướng dẫn cài.
- Ở `npm run dev`, service worker chạy chế độ chỉ-push (không cache), nên thử thông báo được ngay.

## Cài đặt

### 1. PostgreSQL + pgvector và Redis (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgresql-16-pgvector redis-server
sudo systemctl enable --now postgresql redis-server

sudo -u postgres psql -c "CREATE USER web_news WITH PASSWORD 'web_news';"
sudo -u postgres psql -c "CREATE DATABASE web_news OWNER web_news;"
sudo -u postgres psql -d web_news -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # điền GROQ_API_KEY, YOUTUBE_API_KEY
python scripts/generate_vapid_keys.py   # khóa Web Push, rồi sửa VAPID_SUBJECT
python scripts/init_db.py         # Alembic migrations + đồng bộ nguồn/chuyên mục
python scripts/check_llm.py       # thử 2 bước AI với 1 bài mẫu
```

`./setup.sh` làm sẵn venv, `pip install`, `npm install` và tạo các file `.env`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Chạy

```bash
./start-dev.sh
```

Script dọn tiến trình cũ, chạy migration, rồi khởi động FastAPI (:8000), worker và Next.js dev (:3000).
Ctrl+C dừng tất cả. Chạy tay từng phần:

```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000
python -m app.worker                                   # mọi queue + scheduler
WORKER_QUEUES=ai_fast:1,ai_deep:1 python -m app.worker  # thêm 1 worker chỉ chạy AI
cd frontend && npm run dev
```

Chạy nhiều worker cùng lúc là an toàn: chỉ một tiến trình giữ advisory lock và lên lịch.

## Vận hành

```bash
python scripts/pool.py status              # job theo queue, item theo trạng thái, nguồn, token Groq hôm nay
python scripts/pool.py fetch-now [slug]    # cho mọi nguồn (hoặc 1 nguồn) cào ngay, bỏ tạm dừng
python scripts/pool.py requeue-dead        # đưa job `dead` về hàng đợi
python scripts/pool.py rerun summarize     # chạy lại bước tóm tắt cho mọi bài (sau khi đổi prompt/model)
python scripts/remove_source.py <slug>     # xóa hẳn 1 nguồn và mọi bài của nó
alembic revision -m "..."                  # migration mới; `alembic check` báo nếu models.py lệch DB
```

## Cấu trúc thư mục

```text
backend/
  app/
    main.py, routers/        FastAPI: /api/articles, /api/categories, /api/sources, /api/push/*
    models.py                Schema (Alembic quản lý): sources, fetch_runs, topics, items, item_clusters,
                             pipeline_versions, enrichments, jobs, push_subscriptions, deliveries
    constants.py             Danh sách nguồn (connector, priority, trust, lịch) + chuyên mục
    jobs/                    Pool việc: queue.py (enqueue/claim/lease), runner.py, scheduler.py
    pipeline/                Handler từng job: fetch, parse_filter, ai, deliver, maintenance
    connectors/              rss, vietnamnet_jsonld, youtube_api, article_page, http (robots, giãn cách)
    ai/                      providers (Groq, Ollama), prompts + JSON Schema, budget (token), stages
    services/                clustering, hotness, embeddings, raw_store, webpush
    utils/text.py            Chuẩn hóa URL, che dữ liệu cá nhân, SHA-256, SimHash, ngôn ngữ
    worker/__main__.py       python -m app.worker
  migrations/                Alembic
  scripts/                   init_db, check_llm, pool, generate_vapid_keys, remove_source
frontend/
  app/                       layout, feed, category/source pages, manifest.ts, offline
  components/                feed, header (chuyên mục dính trên đầu), push-notifications,
                             ios-install-guide, pwa (đăng ký SW, nút cài app)
  lib/                       api.ts, push.ts
  public/sw.js               Service worker: cache offline + Web Push
```

## Troubleshooting

- **Trang chủ trống:** worker chưa xử lý xong bài nào. Xem `python scripts/pool.py status`.
- **Bài xử lý chậm, nhiều job `rescheduled`:** đang chạm hạn mức Groq (xem mục "AI và hạn mức Groq").
- **Nguồn YouTube báo lỗi:** chưa có `YOUTUBE_API_KEY` trong `backend/.env`. Thêm key rồi chạy
  `python scripts/pool.py fetch-now`.
- **Một nguồn bị `paused`:** lỗi 5 lần liên tiếp (xem `last error` trong `pool.py status`). Sửa xong
  thì `pool.py fetch-now <slug>`.
- **Thông báo không đến:** cần HTTPS khi deploy (localhost là ngoại lệ), `VAPID_*` đã điền, và trên iOS
  phải mở app từ Màn hình chính.
- Model embedding (~470 MB) tự tải từ Hugging Face lần đầu chạy.
