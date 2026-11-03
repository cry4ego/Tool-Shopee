"""Mở phiên trình duyệt cho một tài khoản và kiểm tra phiên đăng nhập còn hạn (F1).

KHÔNG tự động đăng nhập: phiên thiếu hoặc hết hạn → báo lỗi, người dùng chạy lại login.py.
"""
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from config import ACCOUNTS_DIR, LOGIN_URL_MARKERS, SESSION_CHECK_TIMEOUT_MS, SHOPEE_SELLER_URL

logger = logging.getLogger(__name__)

BrowserFactory = Callable[[bool], AbstractContextManager[Browser]]


class SessionError(RuntimeError):
    """Tài khoản không dùng được (chưa đăng nhập / hết hạn). Chưa thao tác gì trên Shopee."""

    def __init__(self, account: str, message: str) -> None:
        super().__init__(message)
        self.account = account


class SessionMissingError(SessionError):
    """Chưa có file accounts/<name>.json."""


class SessionExpiredError(SessionError):
    """Có file trạng thái nhưng Shopee chuyển về trang đăng nhập."""


def state_path(account: str, accounts_dir: str | Path = ACCOUNTS_DIR) -> Path:
    return Path(accounts_dir) / f"{account}.json"


def require_state(account: str, accounts_dir: str | Path = ACCOUNTS_DIR) -> Path:
    """Trả về đường dẫn file trạng thái; ném SessionMissingError nếu chưa đăng nhập."""
    path = state_path(account, accounts_dir)
    if not path.is_file():
        message = f"[{account}] Chưa có trạng thái đăng nhập — chạy: python login.py {account}"
        raise SessionMissingError(account, message)
    return path


def is_login_url(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in LOGIN_URL_MARKERS)


@contextmanager
def chrome_browser(headless: bool = False) -> Iterator[Browser]:
    """Chrome thật (không phải Chromium đi kèm), cùng cấu hình cho đăng nhập và đăng bài."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield browser
        finally:
            browser.close()


@contextmanager
def open_session(
    account: str,
    *,
    headless: bool = False,
    accounts_dir: str | Path = ACCOUNTS_DIR,
    browser_factory: BrowserFactory = chrome_browser,
) -> Iterator[Page]:
    """Mở một BrowserContext riêng với storage_state của tài khoản; luôn đóng trình duyệt khi xong."""
    path = require_state(account, accounts_dir)
    with browser_factory(headless) as browser:
        context = browser.new_context(storage_state=str(path))
        page = context.new_page()
        yield page
        # Chỉ lưu khi khối with chạy xong không lỗi: không ghi đè phiên tốt bằng phiên đã hết hạn
        context.storage_state(path=str(path))
        logger.info("[%s] Đã lưu lại trạng thái đăng nhập", account)


def ensure_logged_in(
    page: Page,
    account: str,
    url: str = SHOPEE_SELLER_URL,
    timeout_ms: int = SESSION_CHECK_TIMEOUT_MS,
) -> None:
    """Mở Seller Centre; nếu bị chuyển về trang đăng nhập trong timeout_ms → SessionExpiredError."""
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_url(is_login_url, timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logger.info("[%s] Phiên đăng nhập còn hạn", account)
        return
    raise SessionExpiredError(account, f"[{account}] Phiên đăng nhập đã hết hạn — chạy: python login.py {account}")
