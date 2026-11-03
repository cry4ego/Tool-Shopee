"""Test phiên đăng nhập (F1) bằng trình duyệt giả — không mở trình duyệt thật."""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from session import (
    SessionExpiredError,
    SessionMissingError,
    ensure_logged_in,
    is_login_url,
    open_session,
    require_state,
)

pytestmark = pytest.mark.unit


class FakeContext:
    def __init__(self) -> None:
        self.saved_to: list[str] = []

    def new_page(self) -> str:
        return "page"

    def storage_state(self, path: str) -> None:
        self.saved_to.append(path)


class FakeBrowser:
    def __init__(self) -> None:
        self.contexts: list[tuple[str, FakeContext]] = []

    def new_context(self, storage_state: str) -> FakeContext:
        context = FakeContext()
        self.contexts.append((storage_state, context))
        return context


class FakeFactory:
    """Thay cho chrome_browser: ghi lại lúc mở/đóng trình duyệt."""

    def __init__(self) -> None:
        self.browser = FakeBrowser()
        self.events: list[str] = []

    @contextmanager
    def __call__(self, headless: bool) -> Iterator[FakeBrowser]:
        self.events.append(f"launch headless={headless}")
        try:
            yield self.browser
        finally:
            self.events.append("close")


@pytest.fixture
def accounts_dir(tmp_path: Path) -> Path:
    (tmp_path / "account_a.json").write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://banhang.shopee.vn/account/signin?next=%2F", True),
        ("https://shopee.vn/buyer/login", True),
        ("https://banhang.shopee.vn/LOGIN", True),
        ("https://banhang.shopee.vn/portal/product/list", False),
        ("https://banhang.shopee.vn/", False),
    ],
)
def test_is_login_url(url: str, expected: bool) -> None:
    assert is_login_url(url) is expected


def test_require_state_missing(tmp_path: Path) -> None:
    with pytest.raises(SessionMissingError, match="python login.py account_a") as exc_info:
        require_state("account_a", tmp_path)

    assert exc_info.value.account == "account_a"


def test_require_state_found(accounts_dir: Path) -> None:
    assert require_state("account_a", accounts_dir) == accounts_dir / "account_a.json"


def test_open_session_missing_state_does_not_launch_browser(tmp_path: Path) -> None:
    factory = FakeFactory()

    with pytest.raises(SessionMissingError):
        with open_session("account_a", accounts_dir=tmp_path, browser_factory=factory):
            pass

    assert factory.events == []


def test_open_session_loads_and_saves_state_then_closes(accounts_dir: Path) -> None:
    factory = FakeFactory()
    state = str(accounts_dir / "account_a.json")

    with open_session("account_a", accounts_dir=accounts_dir, browser_factory=factory) as page:
        assert page == "page"
        assert factory.events == ["launch headless=False"]

    loaded_from, context = factory.browser.contexts[0]
    assert loaded_from == state
    assert context.saved_to == [state]
    assert factory.events == ["launch headless=False", "close"]


def test_open_session_does_not_save_state_on_error_but_still_closes(accounts_dir: Path) -> None:
    factory = FakeFactory()

    with pytest.raises(RuntimeError):
        with open_session("account_a", accounts_dir=accounts_dir, browser_factory=factory):
            raise RuntimeError("lỗi giữa chừng")

    assert factory.browser.contexts[0][1].saved_to == []
    assert factory.events[-1] == "close"


class FakePage:
    def __init__(self, redirects_to_login: bool) -> None:
        self.redirects_to_login = redirects_to_login
        self.visited: list[str] = []

    def goto(self, url: str, wait_until: str) -> None:
        self.visited.append(url)

    def wait_for_url(self, predicate, timeout: int) -> None:
        if not self.redirects_to_login:
            raise PlaywrightTimeoutError("không chuyển trang")


def test_ensure_logged_in_passes_when_no_redirect() -> None:
    page = FakePage(redirects_to_login=False)

    ensure_logged_in(page, "account_a", url="https://seller.test/")

    assert page.visited == ["https://seller.test/"]


def test_ensure_logged_in_raises_when_redirected_to_login() -> None:
    with pytest.raises(SessionExpiredError, match="python login.py account_a"):
        ensure_logged_in(FakePage(redirects_to_login=True), "account_a", url="https://seller.test/")
