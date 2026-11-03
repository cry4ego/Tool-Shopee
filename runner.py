"""Chạy kế hoạch tuần tự (F3): mỗi lúc chỉ một tác vụ, xong hẳn mới sang tác vụ kế tiếp.

Bộ đăng bài (post), hàm chờ (sleep) và đồng hồ (now) được truyền vào, nên test
có thể thay bằng bản giả mà không mở trình duyệt.
"""
import logging
import random
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from captions import build_caption
from config import LATE_GRACE_MINUTES, TASK_DELAY_RANGE
from models import Plan, Task
from session import SessionError
from state_store import StateStore

logger = logging.getLogger(__name__)

SCHEDULE_DISPLAY = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Outcome:
    """Kết quả một lần đăng; status là một trong state_store.STATUSES.

    retryable=True chỉ dùng với "failed" khi CHẮC CHẮN chưa bấm Đăng (thử lại không thể đăng trùng).
    """

    status: str
    message: str = ""
    retryable: bool = False


PostFn = Callable[[Task, str], Outcome]


@dataclass
class RunSummary:
    counts: Counter = field(default_factory=Counter)
    already_done: list[str] = field(default_factory=list)
    not_due: list[str] = field(default_factory=list)
    # Tài khoản bị bỏ qua trong lượt này (chưa đăng nhập / hết phiên) → lý do
    blocked_accounts: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """False nếu có tác vụ lỗi, cần kiểm tra tay, lỡ giờ, hoặc tài khoản bị bỏ qua vì phiên đăng nhập."""
        return not (
            self.counts["failed"] or self.counts["needs_check"] or self.counts["missed"] or self.blocked_accounts
        )


def interleave_by_account(tasks: Iterable[Task]) -> list[Task]:
    """Xen kẽ tài khoản theo thứ tự xuất hiện (A1, B1, A2, B2, A3...), giữ thứ tự trong từng tài khoản."""
    queues: dict[str, list[Task]] = {}
    for task in tasks:
        queues.setdefault(task.account, []).append(task)

    ordered: list[Task] = []
    while queues:
        for account in list(queues):
            ordered.append(queues[account].pop(0))
            if not queues[account]:
                del queues[account]
    return ordered


def run_plan(
    plan: Plan,
    post: PostFn,
    store: StateStore,
    *,
    now: Callable[[], datetime] = datetime.now,
    sleep: Callable[[float], None] = time.sleep,
    delay_range: tuple[int, int] = TASK_DELAY_RANGE,
    rng: random.Random | None = None,
    late_grace: timedelta = timedelta(minutes=LATE_GRACE_MINUTES),
) -> RunSummary:
    """Đăng lần lượt các tác vụ đến giờ và chưa xong; ghi kết quả từng tác vụ vào store.

    Lịch (F5), so với thời điểm bắt đầu lượt chạy:
    - không có schedule_time → đăng ngay;
    - chưa đến giờ → để lượt sau;
    - đã đến giờ, trễ không quá late_grace → đăng;
    - trễ quá late_grace (máy tắt/ngủ quá lâu) → "missed", không đăng nữa.
    """
    rng = rng or random.Random()
    summary = RunSummary()
    current = now()

    runnable: list[Task] = []
    for task in plan.tasks:
        if store.is_done(task.id):
            summary.already_done.append(task.id)
        elif task.schedule_time is not None and task.schedule_time > current:
            summary.not_due.append(task.id)
            logger.info("[%s] Chưa đến giờ (%s)", task.id, task.schedule_time.strftime(SCHEDULE_DISPLAY))
        elif task.schedule_time is not None and current - task.schedule_time > late_grace:
            late_minutes = int((current - task.schedule_time).total_seconds() // 60)
            message = (
                f"Trễ {late_minutes} phút so với giờ hẹn {task.schedule_time.strftime(SCHEDULE_DISPLAY)} "
                f"(cho phép tối đa {int(late_grace.total_seconds() // 60)} phút) — không đăng"
            )
            _finish(task, Outcome("missed", message), store, summary)
        else:
            runnable.append(task)

    ordered = interleave_by_account(runnable)
    attempts = 0
    for index, task in enumerate(ordered):
        blocked_reason = summary.blocked_accounts.get(task.account)
        if blocked_reason is not None:
            _finish(task, Outcome("skipped", blocked_reason), store, summary)
            continue

        if attempts > 0:
            delay = rng.randint(*delay_range)
            logger.info("Chờ %d giây trước tác vụ tiếp theo...", delay)
            sleep(delay)
        attempts += 1

        logger.info("=== Tác vụ %d/%d: [%s] %s %s ===", index + 1, len(ordered), task.id, task.account, task.type)
        caption = build_caption(task, plan.accounts[task.account])
        try:
            outcome = post(task, caption)
        except SessionError as e:
            # Chưa thao tác gì trên Shopee → an toàn để chạy lại sau khi đăng nhập lại
            logger.error("%s", e)
            summary.blocked_accounts[task.account] = str(e)
            outcome = Outcome("skipped", str(e))
        except Exception as e:
            # Không biết lỗi xảy ra trước hay sau khi bấm Đăng → không tự chạy lại
            logger.exception("[%s] Lỗi không mong đợi", task.id)
            outcome = Outcome("needs_check", f"Lỗi không mong đợi: {e}")
        _finish(task, outcome, store, summary)

    _log_summary(summary)
    return summary


def _finish(task: Task, outcome: Outcome, store: StateStore, summary: RunSummary) -> None:
    store.record(task.id, outcome.status, task.account, outcome.message)
    summary.counts[outcome.status] += 1
    logger.info("[%s] Kết quả: %s %s", task.id, outcome.status, outcome.message)


def _log_summary(summary: RunSummary) -> None:
    ran = ", ".join(f"{status}={count}" for status, count in sorted(summary.counts.items())) or "không có"
    logger.info("Tổng kết: đã chạy: %s", ran)
    if summary.already_done:
        logger.info("Bỏ qua vì đã xong từ trước: %s", ", ".join(summary.already_done))
    if summary.not_due:
        logger.info("Chưa đến giờ: %s", ", ".join(summary.not_due))
    for account, reason in summary.blocked_accounts.items():
        logger.warning("Đã bỏ qua mọi tác vụ của %s trong lượt này: %s", account, reason)
    if summary.counts["needs_check"]:
        logger.warning("Có tác vụ needs_check: kiểm tra trên Shopee, xóa mục khỏi file state nếu muốn đăng lại.")
