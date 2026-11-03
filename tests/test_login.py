"""Test login.py: lưu phiên sau khi đăng nhập thủ công, --check lần lượt từng tài khoản."""
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import login
from lock import single_instance
from session import SessionExpiredError, SessionMissingError

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Không ghi log, khóa hay file tài khoản vào thư mục dự án."""
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    monkeypatch.setattr(login, "setup_logging", lambda: None)
    monkeypatch.setattr(login, "LOCK_FILE", tmp_path / "run.lock")
    monkeypatch.setattr(login, "ACCOUNTS_DIR", accounts)
    return accounts


# --- login_and_save ---------------------------------------------------------


class FakePage:
    def __init__(self, url_after_login: str) -> None:
        self.url = "about:blank"
        self.url_after_login = url_after_login

    def goto(self, url: str) -> None:
        self.url = self.url_after_login


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def new_page(self) -> FakePage:
        return self.page

    def storage_state(self, path: str) -> None:
        Path(path).write_text('{"cookies": [], "origins": []}', encoding="utf-8")


def fake_chrome(url_after_login: str):
    @contextmanager
    def factory(headless: bool) -> Iterator[object]:
        assert headless is False  # đăng nhập thủ công luôn hiện trình duyệt

        class Browser:
            def new_context(self) -> FakeContext:
                return FakeContext(FakePage(url_after_login))

        yield Browser()

    return factory


def test_login_saves_state_when_logged_in(isolate: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(login, "chrome_browser", fake_chrome("https://banhang.shopee.vn/portal"))
    monkeypatch.setattr("builtins.input", lambda *args: "")

    assert login.login_and_save("account_a", isolate) is True
    assert (isolate / "account_a.json").is_file()


def test_login_does_not_save_when_still_on_login_page(isolate: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(login, "chrome_browser", fake_chrome("https://banhang.shopee.vn/account/signin"))
    monkeypatch.setattr("builtins.input", lambda *args: "")

    assert login.login_and_save("account_a", isolate) is False
    assert not (isolate / "account_a.json").exists()


# --- list_accounts / check_accounts -----------------------------------------


def test_list_accounts_only_valid_json_names(isolate: Path) -> None:
    for name in ("b.json", "a.json", "ten co dau cach.json", "ghichu.txt"):
        (isolate / name).write_text("{}", encoding="utf-8")

    assert login.list_accounts(isolate) == ["a", "b"]


class FakeOpener:
    """Thay cho open_session; ghi lại thứ tự mở/đóng để kiểm tra tuần tự."""

    def __init__(self, missing: tuple[str, ...] = ()) -> None:
        self.missing = missing
        self.events: list[str] = []

    @contextmanager
    def __call__(self, name: str) -> Iterator[str]:
        if name in self.missing:
            raise SessionMissingError(name, f"[{name}] chưa đăng nhập")
        self.events.append(f"open {name}")
        try:
            yield f"page-{name}"
        finally:
            self.events.append(f"close {name}")


def checker_with(expired: tuple[str, ...] = (), broken: tuple[str, ...] = ()):
    def checker(page: str, name: str) -> None:
        if name in expired:
            raise SessionExpiredError(name, f"[{name}] hết hạn")
        if name in broken:
            raise RuntimeError("mạng lỗi")

    return checker


def test_check_accounts_reports_each_result_sequentially() -> None:
    opener = FakeOpener(missing=("c",))

    results = login.check_accounts(
        ["a", "b", "c", "d"], opener=opener, checker=checker_with(expired=("b",), broken=("d",))
    )

    assert results == {
        "a": login.CHECK_OK,
        "b": login.CHECK_EXPIRED,
        "c": login.CHECK_MISSING,
        "d": login.CHECK_ERROR,
    }
    assert opener.events == ["open a", "close a", "open b", "close b", "open d", "close d"]


# --- main -------------------------------------------------------------------


def test_main_check_all_accounts_ok(isolate: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (isolate / "account_a.json").write_text("{}", encoding="utf-8")
    (isolate / "account_b.json").write_text("{}", encoding="utf-8")
    opener = FakeOpener()
    monkeypatch.setattr(login, "open_session", opener)
    monkeypatch.setattr(login, "ensure_logged_in", checker_with())

    assert login.main(["--check"]) == 0
    assert opener.events == ["open account_a", "close account_a", "open account_b", "close account_b"]


def test_main_check_returns_1_when_any_expired(isolate: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(login, "open_session", FakeOpener())
    monkeypatch.setattr(login, "ensure_logged_in", checker_with(expired=("account_b",)))

    assert login.main(["--check", "account_a", "account_b"]) == 1


def test_main_check_without_accounts_returns_1() -> None:
    assert login.main(["--check"]) == 1


def test_main_returns_2_when_scheduler_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(login, "open_session", FakeOpener())
    monkeypatch.setattr(login, "ensure_logged_in", checker_with())

    with single_instance(login.LOCK_FILE):
        assert login.main(["--check", "account_a"]) == 2


@pytest.mark.parametrize("argv", [["../evil"], ["--check", "a b"], ["account_a", "account_b"]])
def test_main_usage_errors(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        login.main(argv)

    assert exc_info.value.code == 2
