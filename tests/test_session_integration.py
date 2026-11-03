"""Test phiên đăng nhập với trình duyệt thật (headless) trên trang HTML offline."""
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright

from session import SessionExpiredError, ensure_logged_in, open_session

pytestmark = pytest.mark.integration


@contextmanager
def headless_browser(headless: bool) -> Iterator[Browser]:
    """Luôn headless trong test; ưu tiên Chromium đi kèm Playwright, không có thì dùng Chrome."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception as e:
                pytest.skip(f"Không có trình duyệt cho Playwright: {e}")
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def site(tmp_path: Path) -> dict[str, str]:
    """Trang giả: Seller Centre (đã đăng nhập), trang đăng nhập, trang tự chuyển về đăng nhập bằng JS."""
    pages = {
        "seller/index.html": "<h1>Seller Centre</h1>",
        "login/index.html": "<h1>Đăng nhập</h1>",
        "seller/redirect.html": "<script>setTimeout(() => location.href = '../login/index.html', 200)</script>",
    }
    for rel, body in pages.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<!doctype html><meta charset='utf-8'>{body}", encoding="utf-8")
    return {
        "seller": (tmp_path / "seller/index.html").as_uri(),
        "login": (tmp_path / "login/index.html").as_uri(),
        "redirect": (tmp_path / "seller/redirect.html").as_uri(),
    }


@pytest.fixture
def accounts_dir(tmp_path: Path) -> Path:
    path = tmp_path / "accounts"
    path.mkdir()
    (path / "account_a.json").write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
    return path


def test_logged_in_page_passes(site: dict[str, str], accounts_dir: Path) -> None:
    with open_session("account_a", accounts_dir=accounts_dir, browser_factory=headless_browser) as page:
        ensure_logged_in(page, "account_a", url=site["seller"], timeout_ms=500)


@pytest.mark.parametrize("start", ["login", "redirect"])
def test_login_page_or_js_redirect_raises(site: dict[str, str], accounts_dir: Path, start: str) -> None:
    with pytest.raises(SessionExpiredError):
        with open_session("account_a", accounts_dir=accounts_dir, browser_factory=headless_browser) as page:
            ensure_logged_in(page, "account_a", url=site[start], timeout_ms=3000)


def test_state_saved_after_success_not_after_expiry(site: dict[str, str], accounts_dir: Path) -> None:
    state = accounts_dir / "account_a.json"
    old = 1_000_000_000
    os.utime(state, (old, old))

    with pytest.raises(SessionExpiredError):
        with open_session("account_a", accounts_dir=accounts_dir, browser_factory=headless_browser) as page:
            ensure_logged_in(page, "account_a", url=site["login"], timeout_ms=500)
    assert state.stat().st_mtime == old  # phiên hết hạn → không ghi đè file trạng thái

    with open_session("account_a", accounts_dir=accounts_dir, browser_factory=headless_browser) as page:
        ensure_logged_in(page, "account_a", url=site["seller"], timeout_ms=500)
    assert state.stat().st_mtime > old
    assert set(json.loads(state.read_text(encoding="utf-8"))) >= {"cookies", "origins"}
