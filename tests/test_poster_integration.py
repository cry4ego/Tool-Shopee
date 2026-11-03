"""Test poster.py với trình duyệt thật (headless) trên trang Seller Centre giả lập offline."""
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

from models import Task
from poster import post_video

pytestmark = pytest.mark.integration

MOCK_PAGE = (Path(__file__).parent / "fixtures" / "mock_video_upload.html").as_uri()
FAST = {"page_timeout_ms": 3000, "upload_timeout_ms": 3000, "result_timeout_ms": 2000}


@pytest.fixture
def page() -> Iterator[Page]:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception as e:
                pytest.skip(f"Không có trình duyệt cho Playwright: {e}")
        try:
            yield browser.new_page()
        finally:
            browser.close()


@pytest.fixture
def task(tmp_path: Path) -> Task:
    video = tmp_path / "v1.mp4"
    video.write_bytes(b"fake video")
    return Task(id="t001", type="video", account="account_a", video_path=str(video))


def run(page: Page, task: Task, tmp_path: Path, query: str = "", **kwargs):
    return post_video(
        page, task, "Sản phẩm hot\n#hot", url=f"{MOCK_PAGE}?{query}", debug_dir=tmp_path / "debug", **FAST, **kwargs
    )


def debug_files(tmp_path: Path) -> list[str]:
    folder = tmp_path / "debug"
    return sorted(p.suffix for p in folder.iterdir()) if folder.exists() else []


def test_posts_and_confirms_success(page: Page, task: Task, tmp_path: Path) -> None:
    outcome = run(page, task, tmp_path)

    assert outcome.status == "posted"
    assert page.evaluate("window.__posted") == {"caption": "Sản phẩm hot\n#hot", "file": "v1.mp4"}


def test_never_clicks_decoy_buttons(page: Page, task: Task, tmp_path: Path) -> None:
    run(page, task, tmp_path)

    assert page.evaluate("window.__clicked") == ["Đăng"]  # không bấm "Đăng xuất" / "Đăng ký nhận tin"


def test_ticks_hidden_terms_checkbox(page: Page, task: Task, tmp_path: Path) -> None:
    run(page, task, tmp_path)

    assert page.locator("#terms-box").is_checked()


def test_dry_run_fills_everything_but_does_not_submit(page: Page, task: Task, tmp_path: Path) -> None:
    outcome = run(page, task, tmp_path, dry_run=True)

    assert outcome.status == "dry_run"
    assert page.evaluate("window.__clicked") == []
    assert page.evaluate("window.__posted") is None
    assert page.locator("#caption").input_value() == "Sản phẩm hot\n#hot"
    assert page.locator("#terms-box").is_checked()


def test_waits_for_slow_upload_before_submitting(page: Page, task: Task, tmp_path: Path) -> None:
    assert run(page, task, tmp_path, "upload_ms=1500").status == "posted"


def test_upload_never_finishes_is_failed_before_submit(page: Page, task: Task, tmp_path: Path) -> None:
    outcome = run(page, task, tmp_path, "upload_ms=-1")

    assert outcome.status == "failed"
    assert outcome.retryable is True  # chắc chắn chưa bấm Đăng → thử lại an toàn
    assert outcome.message.startswith("Lỗi trước khi bấm Đăng")
    assert page.evaluate("window.__clicked") == []
    assert debug_files(tmp_path) == [".html", ".png"]


def test_missing_upload_button_is_failed(page: Page, task: Task, tmp_path: Path) -> None:
    assert run(page, task, tmp_path, "no_upload=1").status == "failed"


def test_shopee_error_message_is_failed(page: Page, task: Task, tmp_path: Path) -> None:
    outcome = run(page, task, tmp_path, "result=error")

    assert outcome.status == "failed"
    assert outcome.retryable is False  # Shopee từ chối nội dung → gửi lại vẫn bị từ chối
    assert "video không hợp lệ" in outcome.message


def test_no_result_after_submit_needs_check(page: Page, task: Task, tmp_path: Path) -> None:
    outcome = run(page, task, tmp_path, "result=none")

    assert outcome.status == "needs_check"
    assert outcome.retryable is False
    assert page.evaluate("window.__clicked") == ["Đăng"]


# --- on_submit: ghi trạng thái ngay trước khi bấm Đăng (chống đăng trùng khi bị ngắt) ---


def test_on_submit_called_once_right_before_clicking(page: Page, task: Task, tmp_path: Path) -> None:
    clicked_at_mark: list[list[str]] = []

    outcome = run(page, task, tmp_path, on_submit=lambda: clicked_at_mark.append(page.evaluate("window.__clicked")))

    assert outcome.status == "posted"
    assert clicked_at_mark == [[]]  # gọi đúng 1 lần, khi CHƯA bấm Đăng
    assert page.evaluate("window.__clicked") == ["Đăng"]


@pytest.mark.parametrize(("query", "dry_run"), [("", True), ("upload_ms=-1", False)])
def test_on_submit_not_called_when_never_reaching_submit(
    page: Page, task: Task, tmp_path: Path, query: str, dry_run: bool
) -> None:
    marks: list[int] = []

    run(page, task, tmp_path, query, dry_run=dry_run, on_submit=lambda: marks.append(1))

    assert marks == []


def test_on_submit_failure_prevents_clicking(page: Page, task: Task, tmp_path: Path) -> None:
    def disk_full() -> None:
        raise OSError("đĩa đầy — không ghi được state")

    outcome = run(page, task, tmp_path, on_submit=disk_full)

    assert outcome.status == "failed"
    assert outcome.retryable is True  # chưa bấm Đăng → thử lại an toàn
    assert page.evaluate("window.__clicked") == []


def test_error_after_marking_submit_is_needs_check(page: Page, task: Task, tmp_path: Path) -> None:
    """Lỗi xảy ra sau khi đã ghi dấu bấm Đăng (ở đây: trang bị đóng) → needs_check, không retry."""
    outcome = run(page, task, tmp_path, on_submit=page.close)

    assert outcome.status == "needs_check"
    assert outcome.retryable is False
    assert outcome.message.startswith("Lỗi sau khi bấm Đăng")
