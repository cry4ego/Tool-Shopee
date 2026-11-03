"""Đăng một video lên Shopee Seller Centre trên trang đã mở sẵn (F2a).

Quy trình: trang Video → "Tải video lên" → chọn file → chờ tải xong → điền caption
→ đồng ý điều khoản → bấm Đăng → chờ thông báo kết quả.

Phân biệt rõ lỗi TRƯỚC và SAU khi bấm Đăng:
- trước → "failed": chắc chắn chưa đăng, chạy lại an toàn;
- sau, không thấy thông báo → "needs_check": có thể đã đăng, không tự chạy lại (tránh đăng trùng).
Selector nằm ở ui_selectors.py.
"""
import logging
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import ui_selectors as ui
from config import PAGE_TIMEOUT_MS, RESULT_TIMEOUT_MS, SCREENSHOTS_DIR, SHOPEE_VIDEO_URL, UPLOAD_TIMEOUT_MS
from models import Task
from runner import Outcome

logger = logging.getLogger(__name__)


def post_video(
    page: Page,
    task: Task,
    caption: str,
    *,
    dry_run: bool = False,
    url: str = SHOPEE_VIDEO_URL,
    page_timeout_ms: int = PAGE_TIMEOUT_MS,
    upload_timeout_ms: int = UPLOAD_TIMEOUT_MS,
    result_timeout_ms: int = RESULT_TIMEOUT_MS,
    debug_dir: str | Path = SCREENSHOTS_DIR,
    on_submit: Callable[[], None] | None = None,
) -> Outcome:
    """Đăng video của task. dry_run=True: làm hết các bước nhưng KHÔNG bấm Đăng.

    on_submit được gọi ngay TRƯỚC khi bấm Đăng — dùng để ghi needs_check xuống đĩa, để nếu bị
    ngắt (Ctrl+C, tắt máy) sau khi bấm thì lượt sau không đăng lại. on_submit lỗi → không bấm Đăng.
    """
    tag = f"[{task.account}][{task.id}]"
    submitted = False
    try:
        page.goto(url, wait_until="domcontentloaded")

        # === Bước 1-2: mở hộp chọn file và chọn video ===
        upload_btn = _button(page, ui.UPLOAD_BUTTON_NAMES)
        upload_btn.wait_for(timeout=page_timeout_ms)
        with page.expect_file_chooser(timeout=page_timeout_ms) as chooser:
            upload_btn.click()
        chooser.value.set_files(task.video_path)
        logger.info("%s Đã chọn tệp: %s", tag, task.video_path)

        # === Bước 3: chờ tải lên xong — nút Đăng chỉ bật khi video đã lên hết ===
        submit_btn = _button(page, ui.SUBMIT_BUTTON_NAMES)
        expect(submit_btn).to_be_enabled(timeout=upload_timeout_ms)
        logger.info("%s Đã tải video lên xong", tag)

        # === Bước 4: điền caption ===
        if caption:
            caption_box = page.locator(ui.CAPTION_INPUT).first
            caption_box.wait_for(timeout=page_timeout_ms)
            caption_box.fill(caption)
            logger.info("%s Đã điền caption: %r", tag, caption[:50])

        if task.product_id:
            logger.warning("%s Gắn sản phẩm (product_id=%s) chưa được hỗ trợ — bỏ qua", tag, task.product_id)

        # === Bước 5: đồng ý điều khoản ===
        _accept_terms(page, tag)

        if dry_run:
            logger.info("%s [dry-run] Đã điền xong mọi bước, KHÔNG bấm Đăng", tag)
            return Outcome("dry_run", "Đã điền xong, không bấm Đăng")

        # === Bước 6: bấm Đăng và chờ thông báo ===
        if on_submit is not None:
            on_submit()
        submitted = True
        submit_btn.click()
        logger.info("%s Đã bấm Đăng, chờ thông báo kết quả...", tag)
        return _wait_for_result(page, tag, result_timeout_ms)

    except Exception as e:
        logger.exception("%s Lỗi %s khi bấm Đăng", tag, "SAU" if submitted else "TRƯỚC")
        _save_debug(page, task, debug_dir)
        if submitted:
            return Outcome("needs_check", f"Lỗi sau khi bấm Đăng: {e}")
        return Outcome("failed", f"Lỗi trước khi bấm Đăng: {e}", retryable=True)


def _button(page: Page, names: tuple[str, ...]) -> Locator:
    """Nút có tên khớp ĐÚNG một trong các tên (không khớp "Đăng xuất" khi tìm "Đăng")."""
    locator = page.get_by_role("button", name=names[0], exact=True)
    for name in names[1:]:
        locator = locator.or_(page.get_by_role("button", name=name, exact=True))
    return locator.first


def _any_text(page: Page, texts: tuple[str, ...]) -> Locator:
    locator = page.get_by_text(texts[0])
    for text in texts[1:]:
        locator = locator.or_(page.get_by_text(text))
    return locator


def _accept_terms(page: Page, tag: str) -> None:
    label = page.locator("label").filter(has_text=re.compile(ui.TERMS_LABEL_PATTERN, re.IGNORECASE)).first
    if label.count() == 0:
        logger.info("%s Không thấy ô đồng ý điều khoản — bỏ qua", tag)
        return
    checkbox = label.locator('input[type="checkbox"]')
    if checkbox.count() > 0 and checkbox.is_checked():
        return
    label.click()
    if checkbox.count() > 0 and not checkbox.is_checked():
        raise RuntimeError("Không tick được ô đồng ý điều khoản")
    logger.info("%s Đã đồng ý điều khoản", tag)


def _wait_for_result(page: Page, tag: str, timeout_ms: int) -> Outcome:
    success = _any_text(page, ui.SUCCESS_TEXTS)
    failure = _any_text(page, ui.FAILURE_TEXTS)
    try:
        success.or_(failure).first.wait_for(timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logger.warning("%s Không thấy thông báo kết quả sau %d ms", tag, timeout_ms)
        return Outcome("needs_check", "Đã bấm Đăng nhưng không thấy thông báo kết quả — kiểm tra trên Shopee")

    if success.first.is_visible():
        logger.info("%s Shopee báo đăng thành công", tag)
        return Outcome("posted", "Shopee báo đăng thành công")
    message = failure.first.inner_text().strip()
    logger.error("%s Shopee báo lỗi: %s", tag, message)
    return Outcome("failed", f"Shopee báo lỗi: {message}")


def _save_debug(page: Page, task: Task, debug_dir: str | Path) -> None:
    """Lưu ảnh chụp + HTML để gỡ lỗi selector. Không được làm che mất lỗi gốc."""
    base = Path(debug_dir) / f"{datetime.now():%Y%m%d_%H%M%S}_{task.account}_{task.id}"
    try:
        base.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=f"{base}.png", full_page=True)
        Path(f"{base}.html").write_text(page.content(), encoding="utf-8")
        logger.info("Đã lưu ảnh chụp và HTML để gỡ lỗi: %s.png / .html", base)
    except Exception:
        logger.exception("Không lưu được ảnh chụp gỡ lỗi")
