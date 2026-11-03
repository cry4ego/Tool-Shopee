"""Đăng nhập thủ công + kiểm tra phiên đăng nhập (F1). KHÔNG tự điền mật khẩu.

Cách dùng:
    python login.py account_a              # mở Chrome, bạn tự đăng nhập, nhấn Enter để lưu
    python login.py --check                # kiểm tra lần lượt mọi tài khoản trong accounts/
    python login.py --check account_a      # kiểm tra một tài khoản
"""
import argparse
import logging
import sys
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path

from playwright.sync_api import Page

from config import ACCOUNTS_DIR, LOCK_FILE, SHOPEE_SELLER_URL
from lock import LockError, single_instance
from logging_setup import setup_logging
from models import ACCOUNT_NAME_RE
from session import (
    SessionExpiredError,
    SessionMissingError,
    chrome_browser,
    ensure_logged_in,
    is_login_url,
    open_session,
    state_path,
)

logger = logging.getLogger(__name__)

CHECK_OK = "ok"
CHECK_EXPIRED = "hết hạn"
CHECK_MISSING = "chưa đăng nhập"
CHECK_ERROR = "lỗi"


def login_and_save(account_name: str, accounts_dir: str | Path = ACCOUNTS_DIR) -> bool:
    """
    Mở trình duyệt, chờ người dùng đăng nhập thủ công, sau đó lưu trạng thái.
    Trả về False (không lưu) nếu trình duyệt vẫn đang ở trang đăng nhập.
    """
    path = state_path(account_name, accounts_dir)

    with chrome_browser(headless=False) as browser:
        context = browser.new_context()
        page = context.new_page()
        page.goto(SHOPEE_SELLER_URL)

        logger.info("[%s] Vui lòng đăng nhập Shopee Seller Centre trong trình duyệt...", account_name)
        logger.info("Sau khi đăng nhập thành công, nhấn Enter tại đây để lưu trạng thái.")
        input()

        if is_login_url(page.url):
            logger.error("[%s] Trình duyệt vẫn ở trang đăng nhập (%s) — CHƯA lưu. Đăng nhập xong rồi chạy lại.",
                         account_name, page.url)
            return False

        # Lưu cookies + localStorage
        path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(path))
        logger.info("Đã lưu trạng thái vào: %s", path)
        return True


def list_accounts(accounts_dir: str | Path = ACCOUNTS_DIR) -> list[str]:
    """Tên các tài khoản đã có file trạng thái trong accounts/."""
    return sorted(p.stem for p in Path(accounts_dir).glob("*.json") if ACCOUNT_NAME_RE.match(p.stem))


def check_accounts(
    names: Iterable[str],
    *,
    opener: Callable[[str], AbstractContextManager[Page]] = open_session,
    checker: Callable[[Page, str], None] = ensure_logged_in,
) -> dict[str, str]:
    """Kiểm tra lần lượt từng tài khoản — đóng trình duyệt xong mới mở tài khoản kế tiếp."""
    results: dict[str, str] = {}
    for name in names:
        try:
            with opener(name) as page:
                checker(page, name)
            results[name] = CHECK_OK
        except SessionMissingError as e:
            logger.error("%s", e)
            results[name] = CHECK_MISSING
        except SessionExpiredError as e:
            logger.error("%s", e)
            results[name] = CHECK_EXPIRED
        except Exception:
            logger.exception("[%s] Lỗi khi kiểm tra phiên", name)
            results[name] = CHECK_ERROR

    for name, result in results.items():
        logger.info("  %-20s %s", name, result)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Đăng nhập thủ công Shopee Seller Centre và lưu/kiểm tra phiên.")
    parser.add_argument("names", nargs="*", help="tên tài khoản, ví dụ account_a")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm tra phiên còn hạn, không đăng nhập")
    args = parser.parse_args(argv)

    for name in args.names:
        if not ACCOUNT_NAME_RE.match(name):
            parser.error(f"tên tài khoản {name!r} chỉ được chứa chữ, số, '_' và '-'")
    if not args.check and len(args.names) > 1:
        parser.error("mỗi lần chỉ đăng nhập một tài khoản")

    setup_logging()
    # Dùng chung khóa với scheduler.py: không mở trình duyệt khi đang đăng bài
    try:
        with single_instance(LOCK_FILE):
            if not args.check:
                return 0 if login_and_save(args.names[0] if args.names else "account_a") else 1

            names = args.names or list_accounts(ACCOUNTS_DIR)
            if not names:
                logger.warning("Chưa có tài khoản nào trong accounts/ — chạy: python login.py <tên>")
                return 1
            results = check_accounts(names, opener=open_session, checker=ensure_logged_in)
            return 0 if all(r == CHECK_OK for r in results.values()) else 1
    except LockError as e:
        logger.error("%s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
