"""Chạy kế hoạch đăng bài: tuần tự, luân phiên tài khoản, có delay ngẫu nhiên (F3).

Cách dùng:
    python scheduler.py --plan plans/plan.example.json --validate   # chỉ kiểm tra file kế hoạch
    python scheduler.py --plan plans/plan.example.json --fake       # chạy thử, không mở trình duyệt
    python scheduler.py --plan plans/plan.example.json --dry-run    # mở Shopee, điền hết, KHÔNG bấm Đăng
    python scheduler.py --plan plans/plan.example.json              # đăng thật
"""
import argparse
import logging
import sys
import time
from collections.abc import Callable

from captions import build_caption
from config import ACCOUNTS_DIR, LOCK_FILE
from lock import LockError, single_instance
from logging_setup import setup_logging
from models import Plan, Task
from plan_loader import PlanError, load_plan
from poster import post_video
from retry import retry_outcome
from runner import Outcome, PostFn, run_plan
from session import SessionError, ensure_logged_in, open_session
from state_store import StateError, StateStore, state_path_for

logger = logging.getLogger(__name__)


SUBMIT_MARKER_MESSAGE = "Đã bấm Đăng nhưng chưa ghi được kết quả (bị ngắt/tắt máy?) — kiểm tra trên Shopee"


def make_real_post(
    dry_run: bool,
    sleep: Callable[[float], None] = time.sleep,
    on_submit: Callable[[Task], None] | None = None,
) -> PostFn:
    """Bộ đăng thật: mỗi lần thử mở một phiên riêng, kiểm tra đăng nhập, đăng, rồi đóng phiên.

    Lỗi trước khi bấm Đăng được thử lại (retry.py); mỗi lần thử là một phiên trình duyệt mới.
    on_submit(task) được gọi ngay trước khi bấm Đăng (xem execute_plan).
    """

    def real_post(task: Task, caption: str) -> Outcome:
        if task.type != "video":
            return Outcome("skipped", "Bài đăng (post) chưa hỗ trợ — sẽ làm ở GĐ6")
        mark = (lambda: on_submit(task)) if on_submit is not None else None
        return retry_outcome(
            lambda: _attempt_once(task, caption, dry_run, mark), tag=f"[{task.account}][{task.id}]", sleep=sleep
        )

    return real_post


def _attempt_once(task: Task, caption: str, dry_run: bool, on_submit: Callable[[], None] | None) -> Outcome:
    """Một lần thử: mở phiên → kiểm tra đăng nhập → đăng → đóng phiên."""
    outcome: Outcome | None = None
    try:
        with open_session(task.account, accounts_dir=ACCOUNTS_DIR) as page:
            ensure_logged_in(page, task.account)
            outcome = post_video(page, task, caption, dry_run=dry_run, on_submit=on_submit)
    except SessionError:
        raise  # runner bỏ qua các tác vụ còn lại của tài khoản này
    except Exception as e:
        if outcome is not None:
            # Đã có kết quả đăng; lỗi chỉ xảy ra lúc lưu phiên/đóng trình duyệt
            logger.exception("[%s] Lỗi khi đóng phiên sau khi đăng", task.account)
            return outcome
        logger.exception("[%s] Không mở được phiên", task.account)
        return Outcome("failed", f"Không mở được phiên trình duyệt: {e}", retryable=True)
    return outcome


def fake_post(task: Task, caption: str) -> Outcome:
    """Bộ đăng giả cho --fake: chỉ ghi log, không mở trình duyệt."""
    logger.info("[fake] %s đăng %s %s | caption: %r", task.account, task.type, task.id, caption)
    return Outcome("dry_run", "Chạy giả, không mở trình duyệt")


def _fake_sleep(seconds: float) -> None:
    logger.info("[fake] Bỏ qua chờ %s giây", seconds)


def _load(plan_path: str) -> Plan | None:
    try:
        return load_plan(plan_path)
    except PlanError as e:
        logger.error("%s: %s", plan_path, e)
        for error in e.errors:
            logger.error("  - %s", error)
        return None


def validate_plan(plan_path: str) -> int:
    """Kiểm tra file kế hoạch và in caption cuối cùng của từng tác vụ. Trả về mã thoát 0/1."""
    plan = _load(plan_path)
    if plan is None:
        return 1

    logger.info("File kế hoạch hợp lệ: %d tài khoản, %d tác vụ", len(plan.accounts), len(plan.tasks))
    for task in plan.tasks:
        when = task.schedule_time.strftime("%Y-%m-%d %H:%M") if task.schedule_time else "đăng ngay"
        caption = build_caption(task, plan.accounts[task.account])
        logger.info("  [%s] %s | %s | %s | caption: %r", task.id, task.type, task.account, when, caption)
    return 0


def execute_plan(plan_path: str, mode: str = "real") -> int:
    """Chạy kế hoạch dưới khóa một tiến trình. mode: real | dry_run | fake.

    Mã thoát: 0 ổn, 1 có tác vụ lỗi/cần kiểm tra, 2 không chạy được, 130 dừng bằng Ctrl+C.
    Chỉ mode real ghi file state; dry_run/fake giữ kết quả trong bộ nhớ.
    """
    plan = _load(plan_path)
    if plan is None:
        return 1

    try:
        store = StateStore(state_path_for(plan_path) if mode == "real" else None)

        def mark_submitting(task: Task) -> None:
            # Ghi xuống đĩa TRƯỚC khi bấm Đăng: bị ngắt sau đó thì lượt sau không đăng lại
            store.record(task.id, "needs_check", task.account, SUBMIT_MARKER_MESSAGE)

        post: PostFn
        sleep: Callable[[float], None]
        if mode == "fake":
            post, sleep = fake_post, _fake_sleep
        else:
            post, sleep = make_real_post(dry_run=(mode == "dry_run"), on_submit=mark_submitting), time.sleep

        with single_instance(LOCK_FILE):
            summary = run_plan(plan, post, store, sleep=sleep)
    except LockError as e:
        # Bình thường khi Task Scheduler gọi lại trong lúc lượt trước chưa xong
        logger.warning("%s", e)
        return 2
    except StateError as e:
        logger.error("%s", e)
        return 2
    except KeyboardInterrupt:
        # Khóa và trình duyệt đã được nhả/đóng trong các khối with/finally
        logger.warning(
            "Đã dừng bằng Ctrl+C. Tác vụ đã bấm Đăng được ghi needs_check; tác vụ chưa bấm sẽ chạy ở lượt sau."
        )
        return 130
    return 0 if summary.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Đăng video/bài lên Shopee Seller Centre, luân phiên tài khoản.")
    parser.add_argument("--plan", required=True, help="đường dẫn file kế hoạch JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", action="store_true", help="chỉ kiểm tra file kế hoạch, không đăng gì")
    mode.add_argument("--fake", action="store_true", help="chạy thử toàn bộ luồng, không mở trình duyệt")
    mode.add_argument("--dry-run", action="store_true", help="mở Shopee, điền hết các bước nhưng KHÔNG bấm Đăng")
    args = parser.parse_args(argv)

    setup_logging()
    if args.validate:
        return validate_plan(args.plan)
    if args.fake:
        return execute_plan(args.plan, "fake")
    return execute_plan(args.plan, "dry_run" if args.dry_run else "real")


if __name__ == "__main__":
    sys.exit(main())
