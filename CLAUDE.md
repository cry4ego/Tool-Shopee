# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong dự án này. Nội dung trích từ mục 7 "Context dành cho AI" của [README.md](README.md) — kiến trúc, cài đặt, giới hạn đã biết xem README.

> Khi sửa nội dung file này, cập nhật cả README.md mục 7 (và ngược lại) để hai nơi không lệch nhau.

## Tổng quan

Tool local (Python 3.10+, Playwright điều khiển Chrome thật) đăng video lên Shopee Seller Centre, luân phiên nhiều tài khoản.

- `config.py` — hằng số đường dẫn, URL
- `login.py` — đăng nhập thủ công + lưu `storage_state`; `--check` kiểm tra phiên
- `session.py` — `open_session()` / `ensure_logged_in()`: nơi duy nhất nên mở trình duyệt
- `poster.py` — `post_video(page, task, caption, dry_run, on_submit)`; phân biệt lỗi trước (`failed`) / sau khi bấm Đăng (`needs_check`). `on_submit` (từ `scheduler.execute_plan`) ghi `needs_check` xuống đĩa NGAY TRƯỚC khi bấm Đăng — không bỏ bước này, nó chống đăng trùng khi bị Ctrl+C/tắt máy
- `retry.py` — chỉ thử lại `Outcome("failed", retryable=True)` (chắc chắn chưa bấm Đăng). Không đặt `retryable=True` cho lỗi có thể xảy ra sau khi bấm Đăng
- `ui_selectors.py` — mọi selector Seller Centre (chưa xác minh với UI thật). KHÔNG đổi tên thành `selectors.py` (trùng module chuẩn)
- `scheduler.py` — dòng lệnh `--plan/--validate/--fake`, chạy dưới khóa `lock.py`
- `plan_loader.py`, `captions.py`, `models.py` — đọc/kiểm tra file kế hoạch, ghép caption
- `runner.py`, `state_store.py` — chạy tuần tự xen kẽ tài khoản, lưu kết quả chống đăng trùng; chỉ đăng tác vụ đã đến giờ, trễ quá `LATE_GRACE_MINUTES` → `missed`
- `scripts/register_task.ps1` — đăng ký Windows Task Scheduler gọi `scheduler.py` định kỳ (file chỉ dùng ASCII: PowerShell 5.1 đọc UTF-8 không BOM sai)

Rules Python (ECC) nằm trong `.claude/rules/python/`.

## 1. Nguyên tắc bất biến (Invariants)

1. **KHÔNG tự động hóa đăng nhập.** Mọi thay đổi liên quan đến login phải giữ cơ chế "người dùng đăng nhập thủ công → lưu `storage_state`".
2. **Mỗi tài khoản = một `BrowserContext` riêng** với `storage_state` riêng. Không dùng chung context.
3. **Luôn lưu lại `storage_state`** sau mỗi lần đăng video vì cookie có thể được refresh.
4. **Luôn có delay ngẫu nhiên** giữa các tác vụ của các tài khoản khác nhau.
5. **Mặc định `headless=False`** cho mục đích khám phá/quan sát.

## 2. Điểm mở rộng ưu tiên

| Ưu tiên | Việc cần làm | File liên quan |
|---------|--------------|----------------|
| P1 | Đối chiếu selector, `LOGIN_URL_MARKERS`, `MAX_CAPTION_LENGTH` với UI thật; cập nhật trang giả lập cho khớp | `ui_selectors.py`, `config.py`, `tests/fixtures/` |
| P1 | Bài đăng (post) — GĐ6, chờ URL + ảnh chụp form trên Seller Centre | `poster.py`, `ui_selectors.py`, `scheduler.py` |
| P2 | Gắn sản phẩm theo `product_id` | `poster.py`, `ui_selectors.py` |
| P2 | Lệnh đặt lại tác vụ `needs_check`/`missed` thay vì sửa file state bằng tay | `scheduler.py`, `state_store.py` |
| P3 | `--fake` chạy được khi chưa đăng nhập tài khoản nào | `plan_loader.py`, `scheduler.py` |
| P3 | Tương tác chéo (F6): xem + like + comment | module mới `interactor.py` |
| P3 | Hỗ trợ proxy per-context | `config.py`, `session.py` |

## Lệnh kiểm tra

Chạy trước khi báo xong một thay đổi:

```bash
ruff check .
pytest -m unit           # nhanh, không mở trình duyệt
pytest -m integration    # Chromium headless trên trang giả lập offline — không bao giờ truy cập Shopee thật
```

- Test mới đánh dấu `pytestmark = pytest.mark.unit` hoặc `integration` (`--strict-markers`).
- Test không được ghi vào `logs/`, `state/`, `accounts/` của dự án: monkeypatch `setup_logging`, `LOCK_FILE`, `ACCOUNTS_DIR`, `state_path_for` sang `tmp_path` (xem `tests/test_scheduler_cli.py`).
- Code mở trình duyệt nhận factory/page qua tham số để test được (`browser_factory`, `post`, `sleep`, `now`).

## 3. Schema file kế hoạch (`plans/*.json`)

Nguồn chuẩn: README mục 7.3, file mẫu `plans/plan.example.json`, code đọc/kiểm tra ở `plan_loader.py`. Không tự thêm trường mới mà không cập nhật cả ba.

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

- `type`: `"video"` (cần `video_path`) hoặc `"post"` (cần `images`).
- Hashtag ghép theo thứ tự: của task → của tài khoản; bỏ trùng không phân biệt hoa thường (`captions.py`).
- `schedule_time`: `"YYYY-MM-DD HH:MM"` theo giờ máy, hoặc `null` = đăng ngay.
- Khóa lạ bị báo lỗi; mọi lỗi được gom và báo một lần (`PlanError.errors`).

## 4. Cách debug selector

Khi selector trong `poster.py` không khớp:

1. Chạy `python scheduler.py --plan <file> --dry-run` (trình duyệt hiện ra, không bấm Đăng); xem ảnh chụp + HTML trong `logs/screenshots/`.
2. Chèn `page.pause()` vào `poster.py` ngay trước bước lỗi.
3. Trong cửa sổ Playwright Inspector, dùng **"Pick locator"** để lấy selector chính xác.
4. Ưu tiên selector theo thứ tự: `text=`, `role=`, `placeholder=`, rồi mới đến CSS.
5. Sửa trong `ui_selectors.py`, cập nhật trang giả lập `tests/fixtures/mock_video_upload.html`, chạy `pytest -m integration`.

## 5. Những gì KHÔNG nên làm

- Không thêm thư viện nặng (Selenium, Puppeteer) — giữ Playwright làm driver duy nhất.
- Không tự động điền mật khẩu/captcha.
- Không hardcode credential vào code.
- Không chạy song song nhiều tài khoản cùng lúc trên cùng máy (dễ bị phát hiện).
