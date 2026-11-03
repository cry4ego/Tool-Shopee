"""Test chạy kế hoạch tuần tự (F3) bằng bộ đăng giả — không mở trình duyệt."""
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from models import AccountProfile, Plan, Task
from runner import Outcome, interleave_by_account, run_plan
from session import SessionExpiredError
from state_store import StateStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 3, 12, 0)


def make_task(task_id: str, account: str, schedule_time: datetime | None = None) -> Task:
    return Task(
        id=task_id,
        type="video",
        account=account,
        caption=f"cap {task_id}",
        video_path="v.mp4",
        schedule_time=schedule_time,
    )


def make_plan(*tasks: Task) -> Plan:
    accounts = {t.account: AccountProfile(name=t.account, hashtags=("#tag",)) for t in tasks}
    return Plan(accounts=accounts, tasks=tasks)


class FakePoster:
    """Ghi lại mỗi lần mở/đóng phiên để kiểm tra không bao giờ có 2 phiên cùng lúc."""

    def __init__(self, outcomes: dict[str, Outcome] | None = None, raise_for: tuple[str, ...] = ()) -> None:
        self.outcomes = outcomes or {}
        self.raise_for = raise_for
        self.events: list[tuple[str, str]] = []
        self.captions: dict[str, str] = {}
        self.active = 0
        self.max_active = 0

    def __call__(self, task: Task, caption: str) -> Outcome:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.events.append(("open", task.id))
        try:
            self.captions[task.id] = caption
            if task.id in self.raise_for:
                raise RuntimeError("trình duyệt bị đóng")
            return self.outcomes.get(task.id, Outcome("posted"))
        finally:
            self.events.append(("close", task.id))
            self.active -= 1

    @property
    def order(self) -> list[str]:
        return [task_id for event, task_id in self.events if event == "open"]


def run(plan: Plan, poster: FakePoster, store: StateStore | None = None, sleeps: list | None = None):
    return run_plan(
        plan,
        poster,
        store if store is not None else StateStore(None),
        now=lambda: NOW,
        sleep=(sleeps if sleeps is not None else []).append,
        delay_range=(60, 180),
        rng=random.Random(0),
    )


def test_interleave_by_account_keeps_order_within_account() -> None:
    tasks = [make_task(i, a) for i, a in [("a1", "A"), ("a2", "A"), ("a3", "A"), ("b1", "B"), ("c1", "C"), ("b2", "B")]]

    assert [t.id for t in interleave_by_account(tasks)] == ["a1", "b1", "c1", "a2", "b2", "a3"]


def test_runs_tasks_interleaved_by_account() -> None:
    poster = FakePoster()
    plan = make_plan(make_task("a1", "A"), make_task("a2", "A"), make_task("b1", "B"), make_task("b2", "B"))

    run(plan, poster)

    assert poster.order == ["a1", "b1", "a2", "b2"]


def test_never_two_sessions_open_at_once() -> None:
    poster = FakePoster()
    plan = make_plan(*(make_task(f"t{i}", "AB"[i % 2]) for i in range(6)))

    run(plan, poster)

    assert poster.max_active == 1
    # Mỗi phiên đóng xong mới mở phiên kế tiếp: open X, close X, open Y, close Y...
    for i in range(0, len(poster.events), 2):
        opened, closed = poster.events[i], poster.events[i + 1]
        assert opened[0] == "open" and closed == ("close", opened[1])


def test_random_delay_between_consecutive_tasks() -> None:
    sleeps: list[float] = []
    plan = make_plan(make_task("a1", "A"), make_task("b1", "B"), make_task("a2", "A"))

    run(plan, FakePoster(), sleeps=sleeps)

    assert len(sleeps) == 2
    assert all(60 <= s <= 180 for s in sleeps)


def test_no_delay_for_single_task() -> None:
    sleeps: list[float] = []

    run(make_plan(make_task("a1", "A")), FakePoster(), sleeps=sleeps)

    assert sleeps == []


def test_skips_tasks_already_done_and_reruns_others() -> None:
    store = StateStore(None)
    statuses = {"t1": "posted", "t2": "needs_check", "t3": "missed", "t4": "failed", "t5": "skipped", "t6": "dry_run"}
    for task_id, status in statuses.items():
        store.record(task_id, status, "A")
    poster = FakePoster()

    summary = run(make_plan(*(make_task(t, "A") for t in statuses)), poster, store)

    assert poster.order == ["t4", "t5", "t6"]
    assert summary.already_done == ["t1", "t2", "t3"]


def test_future_tasks_are_not_run_yet() -> None:
    poster = FakePoster()
    plan = make_plan(
        make_task("past", "A", NOW - timedelta(minutes=1)),
        make_task("exact", "A", NOW),
        make_task("future", "A", NOW + timedelta(minutes=1)),
        make_task("no_time", "A"),
    )

    summary = run(plan, poster)

    assert poster.order == ["past", "exact", "no_time"]
    assert summary.not_due == ["future"]


def run_scheduled(plan: Plan, poster: FakePoster, store: StateStore, grace_minutes: int = 120):
    return run_plan(
        plan,
        poster,
        store,
        now=lambda: NOW,
        sleep=lambda s: None,
        rng=random.Random(0),
        late_grace=timedelta(minutes=grace_minutes),
    )


def test_late_within_grace_is_posted_beyond_grace_is_missed() -> None:
    store = StateStore(None)
    poster = FakePoster()
    plan = make_plan(
        make_task("late_ok", "A", NOW - timedelta(minutes=119)),
        make_task("at_limit", "A", NOW - timedelta(minutes=120)),
        make_task("too_late", "A", NOW - timedelta(minutes=121)),
    )

    summary = run_scheduled(plan, poster, store)

    assert poster.order == ["late_ok", "at_limit"]
    assert store.get_status("too_late") == "missed"
    assert summary.counts["missed"] == 1
    assert summary.ok is False  # để Task Scheduler báo "last run result" khác 0


def test_missed_message_explains_how_late() -> None:
    store = StateStore(None)
    plan = make_plan(make_task("t1", "A", NOW - timedelta(hours=5)))

    run_scheduled(plan, FakePoster(), store)

    assert store._tasks["t1"]["message"].startswith("Trễ 300 phút so với giờ hẹn 2026-11-03 07:00")


def test_missed_task_is_not_posted_on_later_runs() -> None:
    store = StateStore(None)
    plan = make_plan(make_task("t1", "A", NOW - timedelta(hours=5)))
    run_scheduled(plan, FakePoster(), store)

    poster = FakePoster()
    summary = run_scheduled(plan, poster, store, grace_minutes=10_000)

    assert poster.order == []
    assert summary.already_done == ["t1"]


def test_scheduled_runs_pick_up_tasks_as_they_become_due() -> None:
    """Giả lập Task Scheduler gọi lại mỗi 15 phút: mỗi tác vụ được đăng đúng một lần, khi đến giờ."""
    store = StateStore(None)
    plan = make_plan(
        make_task("now", "A"),
        make_task("t+10", "B", NOW + timedelta(minutes=10)),
        make_task("t+40", "A", NOW + timedelta(minutes=40)),
    )
    posted_by_tick: list[list[str]] = []

    for tick in range(4):  # 12:00, 12:15, 12:30, 12:45
        poster = FakePoster()
        run_plan(plan, poster, store, now=lambda t=tick: NOW + timedelta(minutes=15 * t), sleep=lambda s: None)
        posted_by_tick.append(poster.order)

    assert posted_by_tick == [["now"], ["t+10"], [], ["t+40"]]


def test_unexpected_exception_marks_needs_check_and_continues() -> None:
    store = StateStore(None)
    poster = FakePoster(raise_for=("a1",))

    summary = run(make_plan(make_task("a1", "A"), make_task("b1", "B")), poster, store)

    assert poster.order == ["a1", "b1"]
    assert store.get_status("a1") == "needs_check"
    assert store.get_status("b1") == "posted"
    assert summary.ok is False


def test_session_error_skips_remaining_tasks_of_that_account_only() -> None:
    store = StateStore(None)
    sleeps: list[float] = []
    called: list[str] = []

    def poster(task: Task, caption: str) -> Outcome:
        called.append(task.id)
        if task.account == "A":
            raise SessionExpiredError("A", "[A] Phiên đăng nhập đã hết hạn")
        return Outcome("posted")

    plan = make_plan(make_task("a1", "A"), make_task("a2", "A"), make_task("b1", "B"), make_task("b2", "B"))
    summary = run_plan(plan, poster, store, now=lambda: NOW, sleep=sleeps.append, rng=random.Random(0))

    assert called == ["a1", "b1", "b2"]  # a2 không được thử lại trong lượt này
    assert store.get_status("a1") == "skipped"
    assert store.get_status("a2") == "skipped"
    assert store.get_status("b2") == "posted"
    assert len(sleeps) == 2  # chỉ chờ giữa các lần thật sự mở phiên
    assert "hết hạn" in summary.blocked_accounts["A"]
    assert summary.ok is False


def test_poster_receives_built_caption() -> None:
    poster = FakePoster()

    run(make_plan(make_task("a1", "A")), poster)

    assert poster.captions["a1"] == "cap a1\n#tag"


def test_outcomes_recorded_and_rerun_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "plan.state.json"
    plan = make_plan(make_task("a1", "A"), make_task("b1", "B"))
    first = FakePoster(outcomes={"b1": Outcome("failed", "mạng lỗi")})

    summary = run(plan, first, StateStore(path))
    assert summary.counts == {"posted": 1, "failed": 1}
    assert summary.ok is False

    second = FakePoster()
    run(plan, second, StateStore(path))
    assert second.order == ["b1"]  # a1 đã posted → không đăng lại
