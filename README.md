# Shopee Video Auto-Poster (Local Exploration Tool)

> **Loại dự án**: Script khám phá chạy local, mục đích học hỏi, KHÔNG dùng thương mại.
> **Trạng thái**: F1–F5 đã có và được test trên trang giả lập; **selector chưa đối chiếu với giao diện Shopee thật**. Bài đăng (post) chưa làm.
> **Ngôn ngữ**: Python 3.10+
> **Thư viện chính**: Playwright (điều khiển Chrome thật)

## Mục lục

1. [Mục tiêu dự án](#1-mục-tiêu-dự-án-what--why)
2. [Kiến trúc kỹ thuật](#2-kiến-trúc-kỹ-thuật)
3. [Cài đặt & chạy](#3-cài-đặt--chạy)
4. [Chi tiết từng module](#4-chi-tiết-từng-module)
5. [Điểm dễ vỡ & cách xử lý](#5-điểm-dễ-vỡ--cách-xử-lý)
6. [Giới hạn đã biết](#6-giới-hạn-đã-biết-known-limitations)
7. [Context dành cho AI](#7-context-dành-cho-ai-ai-handoff-section)
8. [Lịch sử phát triển](#8-lịch-sử-phát-triển)
9. [Tuyên bố miễn trừ](#9-tuyên-bố-miễn-trừ)

---

## 1. Mục tiêu dự án (What & Why)

Xây dựng tool local tự động hóa việc **đăng video lên Shopee Seller Centre** thông qua điều khiển trình duyệt Chrome thật, phục vụ mục đích **khám phá kỹ thuật tự động hóa web** — tương tự cách đã làm với script Facebook trước đó.

### 1.1. Yêu cầu chức năng (theo thứ tự ưu tiên)

| #  | Chức năng | Trạng thái | Ghi chú |
|----|-----------|------------|---------|
| F1 | Đăng nhập nhiều tài khoản, lưu trạng thái | ✅ Có | Đăng nhập **thủ công** (`login.py`), kiểm tra phiên bằng `login.py --check` |
| F2 | Đăng video lên Shopee Seller Centre | ✅ Video / ⏳ Bài đăng | `poster.py`; bài đăng (post) chờ thông tin giao diện (GĐ6) |
| F3 | Luân phiên tài khoản, tuyệt đối tuần tự | ✅ Có | `runner.py` + khóa `lock.py`: không bao giờ mở 2 tài khoản cùng lúc |
| F4 | Caption + hashtag riêng theo tài khoản/video | ✅ Có | `captions.py`, khai báo trong file kế hoạch |
| F5 | Tự động lên lịch đăng từ file kế hoạch | ✅ Có | Đăng khi đến giờ; Task Scheduler gọi định kỳ (mục 3.3) |
| F6 | Tương tác chéo (xem/bình luận lẫn nhau) | ⏳ Chưa làm | Phát triển sau cùng, rủi ro cao |

### 1.2. Yêu cầu phi chức năng

- **Không tự động hóa đăng nhập**: tránh kích hoạt captcha/phong tỏa. Người dùng đăng nhập thủ công một lần, script tái sử dụng `storage_state`.
- **Cô lập tài khoản**: mỗi tài khoản dùng `BrowserContext` riêng với `storage_state` riêng.
- **Chạy trên máy cá nhân**: không cần server, không cần Docker.
- **Có thể quan sát**: mặc định `headless=False` để người dùng thấy thao tác.
- **Không đăng trùng**: kết quả từng tác vụ được lưu; chỉ thử lại khi chắc chắn chưa bấm Đăng.

---

## 2. Kiến trúc kỹ thuật

### 2.1. Sơ đồ luồng

```text
 login.py ──(đăng nhập tay)──▶ accounts/<tên>.json (storage_state)
                                         │
 plans/<kế hoạch>.json                   │
        │                                │
        ▼                                ▼
 scheduler.py ──▶ plan_loader ──▶ runner.run_plan()   [giữ khóa state/run.lock]
 (Task Scheduler      (kiểm tra)       │ lần lượt từng tác vụ đã đến giờ,
  gọi định kỳ)                         │ xen kẽ tài khoản, delay ngẫu nhiên
                                       ▼
                         retry ─▶ session.open_session() ─▶ ensure_logged_in()
                                       │                         │
                                       ▼                         ▼
                              poster.post_video() ─────▶ Shopee Seller Centre
                                       │
                                       ▼
                         state/<kế hoạch>.state.json   logs/app.log, logs/screenshots/
```

### 2.2. Cấu trúc thư mục

```text
Scrip Shopee/
├── accounts/                # storage_state từng tài khoản — chứa cookie, KHÔNG chia sẻ
├── videos/                  # Video nguồn
├── plans/
│   └── plan.example.json    # File kế hoạch mẫu (schema: mục 7.3)
├── state/                   # Kết quả từng tác vụ (<kế hoạch>.state.json) + run.lock — tự tạo
├── logs/                    # app.log + screenshots/ khi lỗi — tự tạo
├── scripts/
│   └── register_task.ps1    # Đăng ký Windows Task Scheduler (F5)
├── tests/                   # pytest: unit + integration (trang giả lập trong tests/fixtures/)
├── docs/
│   └── base_goc.md          # Bản gốc base.py (câu trả lời ban đầu), chỉ để tham khảo
├── .claude/rules/python/    # Rules Python của ECC cho Claude Code
├── config.py                # Mọi hằng số cấu hình (mục 4.1)
├── login.py                 # Đăng nhập thủ công, --check
├── session.py               # Mở phiên trình duyệt, phát hiện phiên hết hạn
├── poster.py                # post_video() — đăng video trên trang đã mở
├── ui_selectors.py          # Selector Seller Centre (chưa xác minh)
├── retry.py                 # Thử lại lỗi trước khi bấm Đăng
├── scheduler.py             # Dòng lệnh chính
├── runner.py                # Chạy tuần tự, lịch, tổng kết
├── state_store.py           # Lưu kết quả, chống đăng trùng
├── lock.py                  # Khóa một tiến trình
├── plan_loader.py           # Đọc + kiểm tra file kế hoạch
├── captions.py              # Ghép caption + hashtag
├── models.py                # Task, AccountProfile, Plan
├── logging_setup.py         # Log ra file UTF-8 + console
├── pyproject.toml           # Cấu hình pytest, ruff, coverage
├── requirements.txt / requirements-dev.txt
├── CLAUDE.md                # Hướng dẫn cho Claude Code (trích mục 7)
└── README.md
```

> ⚠️ Các file trong `accounts/` chứa cookie đăng nhập — **không chia sẻ, không đưa lên Git** (đã có trong `.gitignore`).

### 2.3. Quy ước đặt tên

- Tên tài khoản: chỉ chữ, số, `_`, `-` (ví dụ `account_a`). File trạng thái: `accounts/<tên>.json`.
- Hàm public: `snake_case`, có type hint và docstring.
- Selector: chỉ đặt trong `ui_selectors.py`.
- Trạng thái tác vụ: `posted`, `failed`, `needs_check`, `missed`, `skipped`, `dry_run` (`state_store.STATUSES`).

---

## 3. Cài đặt & chạy

### 3.1. Cài đặt

```bash
pip install -r requirements.txt
playwright install chrome   # hoặc dùng Chrome đã cài trên máy
```

### 3.2. Quy trình sử dụng

> Kiểm thử từng chức năng bằng tay trong VS Code: làm theo [docs/kiem_thu_thu_cong.md](docs/kiem_thu_thu_cong.md).

```bash
# Bước 1: Đăng nhập thủ công từng tài khoản (làm 1 lần)
python login.py account_a
python login.py account_b

# Kiểm tra phiên còn hạn (lần lượt từng tài khoản)
python login.py --check

# Bước 2: Đặt video vào videos/, viết file kế hoạch (mẫu: plans/plan.example.json — xem mục 7.3)

# Bước 3: Kiểm tra file kế hoạch, chạy thử không mở trình duyệt
python scheduler.py --plan plans/plan.example.json --validate
python scheduler.py --plan plans/plan.example.json --fake

# Bước 4: Mở Shopee thật, điền hết các bước nhưng KHÔNG bấm Đăng (để kiểm tra selector)
python scheduler.py --plan plans/plan.example.json --dry-run

# Bước 5: Đăng thật (tuần tự, luân phiên tài khoản)
python scheduler.py --plan plans/plan.example.json
```

Kết quả từng tác vụ lưu ở `state/<tên kế hoạch>.state.json`; chạy lại sẽ bỏ qua tác vụ đã `posted`/`needs_check`/`missed`. Muốn đăng lại một tác vụ `needs_check`: kiểm tra trên Shopee trước, rồi xóa mục đó khỏi file state. `--fake` và `--dry-run` không ghi file state.

Mã thoát của `scheduler.py`: `0` ổn · `1` có tác vụ lỗi / cần kiểm tra / lỡ giờ / tài khoản hết phiên, hoặc file kế hoạch lỗi · `2` không chạy được (đang có lượt khác chạy, file state hỏng) · `130` dừng bằng Ctrl+C.

**Dừng giữa chừng (Ctrl+C, tắt máy) an toàn:** ngay trước khi bấm Đăng, tác vụ được ghi `needs_check` xuống file state. Bị ngắt sau đó → lượt sau không đăng lại (kiểm tra trên Shopee rồi tự xử lý); bị ngắt trước khi bấm Đăng → không có gì được ghi, lượt sau chạy lại bình thường. Không ghi được file state thì tool không bấm Đăng.

### 3.3. Lên lịch tự động (F5)

Mỗi lần chạy `scheduler.py` chỉ đăng các tác vụ **đã đến giờ** (`schedule_time` theo giờ của máy; không có giờ = đăng ngay). Tác vụ chưa đến giờ để lượt sau; tác vụ trễ quá `LATE_GRACE_MINUTES` (mặc định 120 phút, `config.py`) bị đánh dấu `missed` và không đăng nữa. Vì vậy chỉ cần gọi `scheduler.py` định kỳ bằng Windows Task Scheduler:

```bash
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Plan plans\thang11.json
```

- Script kiểm tra file kế hoạch trước (`--validate`); kế hoạch lỗi thì không đăng ký gì.
- Mặc định chạy mỗi 15 phút (`-EveryMinutes`), đánh thức máy khi ngủ, bỏ qua lượt mới nếu lượt trước chưa xong. Thêm `-DryRun` để chạy thử không bấm Đăng.
- Chỉ chạy khi bạn đang đăng nhập Windows (Chrome hiện lên để quan sát). Máy tắt hẳn thì không chạy được.
- Gỡ: `powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Remove`.
- Theo dõi: `logs/app.log` và cột "Last Run Result" trong Task Scheduler (mã thoát như mục 3.2).

### 3.4. Chạy test (cho người phát triển)

```bash
pip install -r requirements-dev.txt
pytest -m unit                  # nhanh, không mở trình duyệt
pytest -m integration           # Chromium headless trên trang giả lập offline (tests/fixtures/)
pytest --cov=. --cov-report=term-missing
ruff check .
```

Test integration không bao giờ truy cập Shopee thật. Coverage hiện tại của code nguồn khoảng 97% (160 test).

---

## 4. Chi tiết từng module

### 4.1. `config.py`

| Hằng số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `SHOPEE_SELLER_URL`, `SHOPEE_VIDEO_URL` | `https://banhang.shopee.vn/...` | URL Seller Centre / trang Video |
| `LOGIN_URL_MARKERS` | `/account/signin`, `/buyer/login`, `/login` | Bị chuyển về URL chứa chuỗi này = phiên hết hạn — **chưa xác minh** |
| `SESSION_CHECK_TIMEOUT_MS` | 5 000 | Chờ xem có bị chuyển về trang đăng nhập không |
| `PAGE_TIMEOUT_MS` / `UPLOAD_TIMEOUT_MS` / `RESULT_TIMEOUT_MS` | 15 s / 10 phút / 30 s | Chờ phần tử / tải video xong / thông báo kết quả |
| `TASK_DELAY_RANGE` | (60, 180) giây | Chờ ngẫu nhiên giữa hai tác vụ |
| `RETRY_ATTEMPTS`, `RETRY_BACKOFF_SECONDS` | 3, 30 | Thử lại lỗi trước khi bấm Đăng (30 s, 60 s…) |
| `LATE_GRACE_MINUTES` | 120 | Trễ quá số phút này → `missed` |
| `MAX_CAPTION_LENGTH` | 500 | Độ dài caption tối đa — **chưa xác minh** |
| `LOG_FILE`, `LOG_LEVEL`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT` | `logs/app.log`, INFO, 1 MB, 5 | Log UTF-8 xoay vòng |

### 4.2. `login.py` và `session.py` (F1)

- `python login.py <tên>` → `login_and_save()`: mở Chrome thật (`headless=False`), chờ người dùng đăng nhập rồi nhấn Enter, lưu cookie + localStorage. Nếu trình duyệt vẫn ở trang đăng nhập thì **không lưu**.
- `python login.py --check [tên...]` → `check_accounts()`: mở lần lượt từng tài khoản, báo `ok` / `hết hạn` / `chưa đăng nhập` / `lỗi`.
- Dùng chung khóa với `scheduler.py`; **không** tự động điền form đăng nhập.
- `session.open_session()`: context riêng cho từng tài khoản, luôn đóng trình duyệt, chỉ lưu lại `storage_state` khi không lỗi (không ghi đè phiên tốt bằng phiên hết hạn). `session.ensure_logged_in()`: bị chuyển về URL khớp `LOGIN_URL_MARKERS` → `SessionExpiredError`. Runner gặp lỗi phiên thì bỏ qua các tác vụ còn lại của tài khoản đó trong lượt chạy.

### 4.3. `poster.py`, `ui_selectors.py`, `retry.py` (F2)

Hàm `post_video(page, task, caption, dry_run=False)` chạy trên trang do `session.open_session()` mở sẵn:

- Các bước UI: mở trang Video → bấm "Tải video lên" (bắt hộp chọn file) → chờ nút Đăng bật (video tải xong, tối đa `UPLOAD_TIMEOUT_MS`) → điền caption → bấm nhãn "đồng ý điều khoản" → bấm Đăng → chờ thông báo thành công/thất bại.
- Nút được tìm theo **đúng toàn bộ tên** (không bấm nhầm "Đăng xuất"). Mọi selector nằm ở `ui_selectors.py` — **chưa xác minh với UI thật**.
- Kết quả: `posted` (Shopee báo thành công), `failed` (lỗi trước khi bấm Đăng, hoặc Shopee báo lỗi — chạy lại an toàn), `needs_check` (đã bấm Đăng nhưng không thấy thông báo — không tự chạy lại), `dry_run`.
- Khi lỗi: lưu ảnh chụp + HTML vào `logs/screenshots/<thời điểm>_<tài khoản>_<id>.png/.html`.
- **Retry** (`retry.py`): chỉ thử lại lỗi xảy ra TRƯỚC khi bấm Đăng (và lỗi mở trình duyệt), tối đa `RETRY_ATTEMPTS` lần, chờ `RETRY_BACKOFF_SECONDS` rồi nhân đôi; mỗi lần thử mở một phiên mới. Không bao giờ thử lại `needs_check`, Shopee từ chối, hay lỗi phiên đăng nhập.
- Chưa hỗ trợ gắn sản phẩm (`product_id` chỉ được ghi cảnh báo).

### 4.4. `scheduler.py`, `runner.py`, `state_store.py`, `lock.py` (F3, F5)

- Dòng lệnh: `--plan <file>` (bắt buộc) kèm một trong `--validate` (chỉ kiểm tra), `--fake` (chạy thử, không mở trình duyệt), `--dry-run` (mở Shopee, không bấm Đăng); không kèm gì = đăng thật.
- Chạy dưới khóa `state/run.lock` (`lock.py`, khóa của hệ điều hành — tự nhả khi tiến trình chết; dùng chung với `login.py`): không bao giờ có 2 tài khoản mở cùng lúc.
- `runner.run_plan()`: bỏ qua tác vụ đã xong, chưa đến giờ, hoặc lỡ giờ (`missed`); xen kẽ tài khoản (A, B, A, B…); chờ ngẫu nhiên `TASK_DELAY_RANGE` giây giữa hai lần mở phiên; ghi kết quả vào `state_store` sau **mỗi** tác vụ.
- `state_store`: ghi file tạm rồi `os.replace` (không hỏng file khi bị tắt ngang); file state hỏng → dừng, không ghi đè.

### 4.5. `plan_loader.py`, `captions.py`, `models.py` (F4)

- `load_plan()`: đọc file kế hoạch, kiểm tra toàn bộ và báo **mọi lỗi một lần** (`PlanError.errors`), kèm vị trí `tasks[i] (id=...)`. Khóa gõ nhầm, file media không tồn tại, tài khoản chưa đăng nhập, caption quá dài đều bị báo.
- `build_caption()`: caption + hashtag của task + hashtag của tài khoản, tự thêm `#`, bỏ trùng không phân biệt hoa thường, bỏ hashtag đã có trong caption.

---

## 5. Điểm dễ vỡ & cách xử lý

| Vấn đề | Nguyên nhân | Cách xử lý |
|--------|-------------|------------|
| Selector sai | UI Shopee thay đổi theo khu vực/phiên bản | Xem `logs/screenshots/`, chạy `--dry-run`, sửa `ui_selectors.py` (mục 7.4) |
| Tải video chậm | Video lớn, mạng chậm | Tăng `UPLOAD_TIMEOUT_MS` |
| Cookie hết hạn | Session timeout | `python login.py --check`, rồi `python login.py <tài khoản>` |
| Tác vụ `needs_check` | Đã bấm Đăng nhưng không thấy thông báo, hoặc bị Ctrl+C/tắt máy sau khi bấm Đăng | Kiểm tra trên Shopee; muốn đăng lại thì xóa mục đó khỏi file state |
| Tác vụ `missed` | Máy tắt/ngủ quá `LATE_GRACE_MINUTES` lúc đến giờ | Đổi `schedule_time` + `id` mới trong file kế hoạch |
| Bị phong tỏa | Nhiều tài khoản cùng IP/fingerprint | Giới hạn số tài khoản, chèn delay dài, cân nhắc proxy |

---

## 6. Giới hạn đã biết (Known Limitations)

- **Selector, `LOGIN_URL_MARKERS`, `MAX_CAPTION_LENGTH` là phỏng đoán**: mới test trên trang giả lập, chưa đối chiếu với Seller Centre thật.
- **Chưa có bài đăng (post)**: tác vụ `type: "post"` được đánh dấu `skipped` (GĐ6).
- **Chưa gắn sản phẩm**: `product_id` bị bỏ qua (chỉ ghi cảnh báo).
- **Không cô lập IP/fingerprint**: các `BrowserContext` chỉ cô lập cookie và localStorage, nhưng chia sẻ cùng IP máy và fingerprint trình duyệt. Chạy nhiều tài khoản trên một máy có rủi ro bị liên kết.
- **Số lượng tài khoản**: code không giới hạn số tài khoản, nhưng càng nhiều tài khoản trên cùng một IP thì rủi ro càng cao.
- **Chưa có tương tác chéo (F6)**: xem/bình luận lẫn nhau chưa được triển khai.
- **Lên lịch (F5) chạy tại máy**: máy phải bật và bạn phải đang đăng nhập Windows lúc đến giờ. Chưa dùng tính năng hẹn giờ có sẵn của Shopee.
- **`--fake` vẫn đòi tài khoản đã đăng nhập** (dùng chung bước kiểm tra file kế hoạch với chế độ thật).
- **Khóa trên Linux/macOS** (`fcntl`) có code nhưng chưa được test trên máy thật.
- **Không hỗ trợ đa nền tảng**: chỉ Shopee, không TikTok/Facebook.
- **Không có GUI**: chỉ CLI.

---

## 7. Context dành cho AI (AI Handoff Section)

> Phần này dành cho AI đọc để tiếp tục phát triển dự án. **Đọc kỹ trước khi sửa code.**

### 7.1. Nguyên tắc bất biến (Invariants)

1. **KHÔNG tự động hóa đăng nhập.** Mọi thay đổi liên quan đến login phải giữ cơ chế "người dùng đăng nhập thủ công → lưu `storage_state`".
2. **Mỗi tài khoản = một `BrowserContext` riêng** với `storage_state` riêng. Không dùng chung context.
3. **Luôn lưu lại `storage_state`** sau mỗi lần đăng video vì cookie có thể được refresh.
4. **Luôn có delay ngẫu nhiên** giữa các tác vụ của các tài khoản khác nhau.
5. **Mặc định `headless=False`** cho mục đích khám phá/quan sát.

### 7.2. Điểm mở rộng ưu tiên

| Ưu tiên | Việc cần làm | File liên quan |
|---------|--------------|----------------|
| P1 | Đối chiếu selector, `LOGIN_URL_MARKERS`, `MAX_CAPTION_LENGTH` với UI thật; cập nhật trang giả lập cho khớp | `ui_selectors.py`, `config.py`, `tests/fixtures/` |
| P1 | Bài đăng (post) — GĐ6, chờ URL + ảnh chụp form trên Seller Centre | `poster.py`, `ui_selectors.py`, `scheduler.py` |
| P2 | Gắn sản phẩm theo `product_id` | `poster.py`, `ui_selectors.py` |
| P2 | Lệnh đặt lại tác vụ `needs_check`/`missed` thay vì sửa file state bằng tay | `scheduler.py`, `state_store.py` |
| P3 | `--fake` chạy được khi chưa đăng nhập tài khoản nào | `plan_loader.py`, `scheduler.py` |
| P3 | Tương tác chéo (F6): xem + like + comment | module mới `interactor.py` |
| P3 | Hỗ trợ proxy per-context | `config.py`, `session.py` |

### 7.3. Schema file kế hoạch (`plans/*.json`)

File mẫu: `plans/plan.example.json`. Kiểm tra trước khi chạy: `python scheduler.py --plan <file> --validate`.

```json
{
  "accounts": {
    "account_a": { "hashtags": ["#shopeevn", "#sale"] }
  },
  "tasks": [
    {
      "id": "t001",
      "type": "video",
      "account": "account_a",
      "video_path": "videos/video1.mp4",
      "caption": "Sản phẩm hot",
      "hashtags": ["#hot"],
      "schedule_time": "2026-11-03 14:00",
      "product_id": null
    }
  ]
}
```

| Trường của task | Bắt buộc | Ghi chú |
|-----------------|----------|---------|
| `id` | ✅ | Chuỗi, không trùng |
| `type` | ✅ | `"video"` hoặc `"post"` |
| `account` | ✅ | Phải có trong `accounts` và đã đăng nhập (`accounts/<tên>.json`) |
| `video_path` | Với `video` | Đường dẫn tương đối tính từ thư mục dự án |
| `images` | Với `post` | Danh sách ít nhất 1 ảnh |
| `caption` | | Chuỗi |
| `hashtags` | | Ghép theo thứ tự: hashtag của task → hashtag của tài khoản; bỏ trùng không phân biệt hoa thường |
| `schedule_time` | | `"YYYY-MM-DD HH:MM"` theo giờ máy, hoặc `null` = đăng ngay |
| `product_id` | | Chuỗi, số hoặc `null` |

Khóa không có trong bảng sẽ bị báo lỗi (để bắt lỗi gõ nhầm). Caption sau khi ghép hashtag không vượt `MAX_CAPTION_LENGTH` trong `config.py`.

### 7.4. Cách debug selector

Khi selector không khớp (xem ảnh chụp + HTML trong `logs/screenshots/`):

1. Chạy `python scheduler.py --plan <file> --dry-run` (trình duyệt hiện ra, không bấm Đăng).
2. Chèn `page.pause()` vào `poster.py` ngay trước bước lỗi.
3. Trong cửa sổ Playwright Inspector, dùng **"Pick locator"** để lấy selector chính xác.
4. Ưu tiên selector theo thứ tự: `text=`, `role=`, `placeholder=`, rồi mới đến CSS.
5. Sửa trong `ui_selectors.py`, rồi cập nhật trang giả lập `tests/fixtures/mock_video_upload.html` cho giống UI thật và chạy `pytest -m integration`.

### 7.5. Những gì KHÔNG nên làm

- Không thêm thư viện nặng (Selenium, Puppeteer) — giữ Playwright làm driver duy nhất.
- Không tự động điền mật khẩu/captcha.
- Không hardcode credential vào code.
- Không chạy song song nhiều tài khoản cùng lúc trên cùng máy (dễ bị phát hiện).

---

## 8. Lịch sử phát triển

| Giai đoạn | Nội dung | Trạng thái |
|-----------|----------|------------|
| G1 | Base code: config, login, poster, scheduler | ✅ Hoàn thành |
| G1.1 | Tách `base.py` thành các module riêng, chuẩn hóa README, thêm CLAUDE.md | ✅ Hoàn thành |
| GĐ0 | Logging ra file UTF-8, bộ khung test, pytest/ruff | ✅ Hoàn thành |
| GĐ1 | File kế hoạch JSON, kiểm tra hợp lệ, ghép caption/hashtag (F4) | ✅ Hoàn thành |
| GĐ2 | Chạy tuần tự xen kẽ tài khoản, lưu kết quả, khóa một tiến trình (F3) | ✅ Hoàn thành |
| GĐ3 | Phiên đăng nhập: `session.py`, `login.py --check` (F1) | ✅ Hoàn thành |
| GĐ4 | Viết lại `poster.py`, sửa selector, `--dry-run` (F2 video) | ✅ Hoàn thành |
| GĐ5 | Retry an toàn (chỉ trước khi bấm Đăng) | ✅ Hoàn thành |
| GĐ6 | Bài đăng (F2 post) | ⏳ Chờ thông tin giao diện |
| GĐ7 | Lên lịch: đăng khi đến giờ, `missed`, Task Scheduler (F5) | ✅ Hoàn thành |
| GĐ8 | Hoàn thiện tài liệu, coverage | ✅ Hoàn thành |
| — | Đối chiếu selector với Shopee thật | ⏳ Cần người dùng chạy `--dry-run` |
| G4 | Tương tác chéo | ⏳ Chờ |

---

## 9. Tuyên bố miễn trừ

Dự án này phục vụ mục đích khám phá và học hỏi kỹ thuật tự động hóa web. Không dùng cho mục đích thương mại, không dùng để spam hoặc thao túng nền tảng. Người dùng tự chịu trách nhiệm về việc tuân thủ điều khoản dịch vụ của Shopee.
