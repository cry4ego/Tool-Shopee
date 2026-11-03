"""Test dòng lệnh scheduler.py (--validate, --fake, chạy thật với bộ đăng giả)."""
import functools
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import scheduler
from lock import single_instance
from models import Task
from plan_loader import load_plan
from runner import Outcome
from session import SessionMissingError

pytestmark = pytest.mark.unit


@pytest.fixture
def plan_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Kế hoạch hợp lệ trong thư mục tạm; log, khóa và state không đụng tới thư mục dự án."""
    (tmp_path / "accounts").mkdir()
    for name in ("account_a", "account_b"):
        (tmp_path / "accounts" / f"{name}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "v1.mp4").write_bytes(b"fake")
    plan = {
        "accounts": {"account_a": {"hashtags": ["#shopeevn"]}, "account_b": {}},
        "tasks": [
            {"id": "a1", "type": "video", "account": "account_a", "video_path": "v1.mp4", "caption": "Hot"},
            {"id": "a2", "type": "video", "account": "account_a", "video_path": "v1.mp4"},
            {"id": "b1", "type": "video", "account": "account_b", "video_path": "v1.mp4"},
        ],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    monkeypatch.setattr(scheduler, "setup_logging", lambda: None)
    monkeypatch.setattr(
        scheduler, "load_plan", functools.partial(load_plan, base_dir=tmp_path, accounts_dir=tmp_path / "accounts")
    )
    monkeypatch.setattr(scheduler, "LOCK_FILE", tmp_path / "run.lock")
    monkeypatch.setattr(scheduler, "state_path_for", lambda plan_path: tmp_path / "plan.state.json")
    return path


def test_validate_valid_plan_returns_0(plan_file: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        code = scheduler.main(["--plan", str(plan_file), "--validate"])

    assert code == 0
    assert "File kế hoạch hợp lệ: 2 tài khoản, 3 tác vụ" in caplog.text
    assert "'Hot\\n#shopeevn'" in caplog.text


def test_validate_invalid_plan_returns_1_and_lists_errors(
    plan_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    data = json.loads(plan_file.read_text(encoding="utf-8"))
    data["tasks"][0]["type"] = "reel"
    plan_file.write_text(json.dumps(data), encoding="utf-8")

    code = scheduler.main(["--plan", str(plan_file), "--validate"])

    assert code == 1
    assert "'type' phải là một trong" in caplog.text


def test_fake_run_interleaves_accounts_without_browser(plan_file: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        code = scheduler.main(["--plan", str(plan_file), "--fake"])

    assert code == 0
    fake_lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[fake] account_")]
    assert [line.split()[4] for line in fake_lines] == ["a1", "b1", "a2"]
    assert not (plan_file.parent / "plan.state.json").exists()  # --fake không ghi state


def test_real_run_records_state_and_skips_posted_next_time(
    plan_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted: list[str] = []

    def fake_real_post(task: Task, caption: str) -> Outcome:
        posted.append(task.id)
        return Outcome("posted")

    monkeypatch.setattr(scheduler, "make_real_post", lambda dry_run, **kwargs: fake_real_post)
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: None)

    assert scheduler.main(["--plan", str(plan_file)]) == 0
    assert scheduler.main(["--plan", str(plan_file)]) == 0

    assert posted == ["a1", "b1", "a2"]  # lần chạy thứ hai không đăng lại gì
    state = json.loads((plan_file.parent / "plan.state.json").read_text(encoding="utf-8"))
    assert {k: v["status"] for k, v in state["tasks"].items()} == {"a1": "posted", "b1": "posted", "a2": "posted"}


def test_returns_2_when_another_instance_is_running(plan_file: Path, caplog: pytest.LogCaptureFixture) -> None:
    with single_instance(scheduler.LOCK_FILE):
        code = scheduler.main(["--plan", str(plan_file), "--fake"])

    assert code == 2
    assert "đang chạy" in caplog.text


def test_returns_2_when_state_file_is_corrupt(plan_file: Path) -> None:
    (plan_file.parent / "plan.state.json").write_text("{ hỏng", encoding="utf-8")

    assert scheduler.main(["--plan", str(plan_file)]) == 2


def test_dry_run_uses_browser_poster_without_writing_state(
    plan_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modes: list[bool] = []

    def make_fake(dry_run: bool, **kwargs):
        modes.append(dry_run)
        return lambda task, caption: Outcome("dry_run")

    monkeypatch.setattr(scheduler, "make_real_post", make_fake)
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: None)

    assert scheduler.main(["--plan", str(plan_file), "--dry-run"]) == 0
    assert modes == [True]
    assert not (plan_file.parent / "plan.state.json").exists()


@pytest.mark.parametrize(
    "argv",
    [[], ["--validate"], ["--plan", "x.json", "--validate", "--fake"], ["--plan", "x.json", "--fake", "--dry-run"]],
)
def test_usage_errors(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "setup_logging", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        scheduler.main(argv)

    assert exc_info.value.code == 2


# --- make_real_post: mở phiên → kiểm tra đăng nhập → đăng → đóng phiên ---------------


def make_task(task_type: str = "video") -> Task:
    return Task(id="t1", type=task_type, account="account_a", video_path="v.mp4")


class FakeSession:
    """Thay cho open_session; open_errors: lỗi ném ra ở các lần mở đầu tiên (theo thứ tự)."""

    def __init__(self, open_errors: tuple[Exception, ...] = (), fail_close: Exception | None = None) -> None:
        self.open_errors = list(open_errors)
        self.fail_close = fail_close
        self.opens = 0
        self.events: list[str] = []

    @contextmanager
    def __call__(self, account: str, accounts_dir: Path) -> Iterator[str]:
        self.opens += 1
        if self.open_errors:
            raise self.open_errors.pop(0)
        self.events.append(f"open {account}")
        yield "page"
        self.events.append(f"close {account}")
        if self.fail_close:
            raise self.fail_close


@dataclass
class BrowserCalls:
    steps: list[str] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)  # kết quả post_video lần lượt; hết → thành công
    # id tác vụ → "before"/"after": giả lập Ctrl+C trước / sau khi bấm Đăng
    interrupt: dict[str, str] = field(default_factory=dict)


@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch) -> BrowserCalls:
    calls = BrowserCalls()
    monkeypatch.setattr(scheduler, "ensure_logged_in", lambda page, account: calls.steps.append("check login"))

    def fake_post_video(page: str, task: Task, caption: str, dry_run: bool, on_submit=None) -> Outcome:
        calls.steps.append(f"post dry_run={dry_run}")
        if calls.interrupt.get(task.id) == "before":
            raise KeyboardInterrupt
        if calls.outcomes:
            return calls.outcomes.pop(0)
        if not dry_run and on_submit is not None:
            on_submit()  # như poster.py: ghi trạng thái ngay trước khi bấm Đăng
        if calls.interrupt.get(task.id) == "after":
            raise KeyboardInterrupt
        return Outcome("dry_run" if dry_run else "posted")

    monkeypatch.setattr(scheduler, "post_video", fake_post_video)
    return calls


def real_post(sleeps: list[float], dry_run: bool = False):
    return scheduler.make_real_post(dry_run, sleep=sleeps.append)


def test_real_post_skips_feed_posts_until_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "open_session", lambda *a, **k: pytest.fail("không được mở trình duyệt"))

    assert real_post([])(make_task("post"), "cap").status == "skipped"


@pytest.mark.parametrize(("dry_run", "status"), [(False, "posted"), (True, "dry_run")])
def test_real_post_checks_login_then_posts(
    monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls, dry_run: bool, status: str
) -> None:
    session = FakeSession()
    monkeypatch.setattr(scheduler, "open_session", session)

    assert real_post([], dry_run)(make_task(), "cap").status == status
    assert browser.steps == ["check login", f"post dry_run={dry_run}"]
    assert session.events == ["open account_a", "close account_a"]


def test_real_post_session_errors_reach_runner_without_retry(
    monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls
) -> None:
    session = FakeSession(open_errors=(SessionMissingError("account_a", "chưa"),))
    monkeypatch.setattr(scheduler, "open_session", session)
    sleeps: list[float] = []

    with pytest.raises(SessionMissingError):
        real_post(sleeps)(make_task(), "cap")
    assert session.opens == 1
    assert sleeps == []


def test_real_post_retries_browser_launch_failure(monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls) -> None:
    session = FakeSession(open_errors=(RuntimeError("không có Chrome"), RuntimeError("không có Chrome")))
    monkeypatch.setattr(scheduler, "open_session", session)
    sleeps: list[float] = []

    assert real_post(sleeps)(make_task(), "cap").status == "posted"
    assert session.opens == 3
    assert sleeps == [30, 60]
    assert session.events == ["open account_a", "close account_a"]  # mỗi lần thử là một phiên mới


def test_real_post_gives_up_after_max_launch_failures(monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls) -> None:
    monkeypatch.setattr(scheduler, "open_session", FakeSession(open_errors=(RuntimeError("không có Chrome"),) * 3))

    outcome = real_post([])(make_task(), "cap")

    assert outcome.status == "failed"
    assert outcome.message.endswith("(đã thử 3 lần)")
    assert browser.steps == []


def test_real_post_retries_failure_before_submit(monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls) -> None:
    session = FakeSession()
    monkeypatch.setattr(scheduler, "open_session", session)
    browser.outcomes = [Outcome("failed", "Lỗi trước khi bấm Đăng: timeout", retryable=True)]

    assert real_post([])(make_task(), "cap").status == "posted"
    assert browser.steps.count("post dry_run=False") == 2
    assert session.events == ["open account_a", "close account_a"] * 2


@pytest.mark.parametrize(
    "outcome",
    [Outcome("failed", "Shopee báo lỗi: video không hợp lệ"), Outcome("needs_check", "không thấy thông báo")],
)
def test_real_post_never_retries_after_submit_or_rejection(
    monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls, outcome: Outcome
) -> None:
    monkeypatch.setattr(scheduler, "open_session", FakeSession())
    browser.outcomes = [outcome]
    sleeps: list[float] = []

    assert real_post(sleeps)(make_task(), "cap") == outcome
    assert browser.steps.count("post dry_run=False") == 1
    assert sleeps == []


def test_real_post_keeps_result_when_closing_session_fails(
    monkeypatch: pytest.MonkeyPatch, browser: BrowserCalls
) -> None:
    monkeypatch.setattr(scheduler, "open_session", FakeSession(fail_close=RuntimeError("đĩa đầy")))

    assert real_post([])(make_task(), "cap").status == "posted"


# --- Ctrl+C: tác vụ đã bấm Đăng không bao giờ bị đăng lại -------------------------


def read_state(plan_file: Path) -> dict[str, dict]:
    path = plan_file.parent / "plan.state.json"
    return json.loads(path.read_text(encoding="utf-8"))["tasks"] if path.exists() else {}


@pytest.fixture
def real_run(plan_file: Path, browser: BrowserCalls, monkeypatch: pytest.MonkeyPatch) -> BrowserCalls:
    """Chạy đăng thật qua make_real_post thật, chỉ thay trình duyệt bằng bản giả."""
    monkeypatch.setattr(scheduler, "open_session", FakeSession())
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: None)
    return browser


def test_ctrl_c_after_submit_marks_needs_check_and_is_not_reposted(
    plan_file: Path, real_run: BrowserCalls, caplog: pytest.LogCaptureFixture
) -> None:
    real_run.interrupt = {"b1": "after"}  # thứ tự chạy: a1, b1, a2

    assert scheduler.main(["--plan", str(plan_file)]) == 130
    state = read_state(plan_file)
    assert state["a1"]["status"] == "posted"
    assert state["b1"]["status"] == "needs_check"
    assert state["b1"]["message"] == scheduler.SUBMIT_MARKER_MESSAGE
    assert "a2" not in state
    assert "Ctrl+C" in caplog.text

    real_run.interrupt = {}
    real_run.steps.clear()
    assert scheduler.main(["--plan", str(plan_file)]) == 0
    assert real_run.steps.count("post dry_run=False") == 1  # chỉ a2; b1 không bị đăng lại
    assert read_state(plan_file)["b1"]["status"] == "needs_check"


def test_ctrl_c_before_submit_leaves_task_to_run_next_time(plan_file: Path, real_run: BrowserCalls) -> None:
    real_run.interrupt = {"b1": "before"}

    assert scheduler.main(["--plan", str(plan_file)]) == 130
    assert "b1" not in read_state(plan_file)  # chưa bấm Đăng → không ghi gì → lượt sau chạy lại

    real_run.interrupt = {}
    assert scheduler.main(["--plan", str(plan_file)]) == 0
    assert {k: v["status"] for k, v in read_state(plan_file).items()} == {
        "a1": "posted",
        "b1": "posted",
        "a2": "posted",
    }


def test_lock_is_released_after_ctrl_c(plan_file: Path, real_run: BrowserCalls) -> None:
    real_run.interrupt = {"a1": "after"}
    assert scheduler.main(["--plan", str(plan_file)]) == 130

    with single_instance(scheduler.LOCK_FILE):
        pass


def test_dry_run_never_writes_submit_marker(plan_file: Path, real_run: BrowserCalls) -> None:
    assert scheduler.main(["--plan", str(plan_file), "--dry-run"]) == 0
    assert read_state(plan_file) == {}
