"""Test retry an toàn: chỉ thử lại lỗi TRƯỚC khi bấm Đăng (GĐ5)."""
import pytest

from retry import retry_outcome
from runner import Outcome
from session import SessionExpiredError

pytestmark = pytest.mark.unit

RETRYABLE = Outcome("failed", "mạng chập chờn", retryable=True)


class Attempts:
    """Trả lần lượt các kết quả cho trước; ghi lại số lần được gọi."""

    def __init__(self, *outcomes: Outcome | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self) -> Outcome:
        self.calls += 1
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def run(attempt: Attempts, sleeps: list[float], attempts: int = 3) -> Outcome:
    return retry_outcome(attempt, attempts=attempts, backoff_seconds=30, sleep=sleeps.append)


def test_succeeds_after_retryable_failures_with_doubling_backoff() -> None:
    sleeps: list[float] = []
    attempt = Attempts(RETRYABLE, RETRYABLE, Outcome("posted"))

    assert run(attempt, sleeps).status == "posted"
    assert attempt.calls == 3
    assert sleeps == [30, 60]


def test_gives_up_after_max_attempts() -> None:
    sleeps: list[float] = []
    attempt = Attempts(RETRYABLE, RETRYABLE, RETRYABLE)

    outcome = run(attempt, sleeps)

    assert outcome.status == "failed"
    assert outcome.message == "mạng chập chờn (đã thử 3 lần)"
    assert attempt.calls == 3
    assert sleeps == [30, 60]  # không chờ sau lần cuối


@pytest.mark.parametrize(
    "outcome",
    [
        Outcome("posted"),
        Outcome("dry_run"),
        Outcome("needs_check", "đã bấm Đăng, không thấy thông báo"),
        Outcome("failed", "Shopee báo lỗi: video không hợp lệ"),  # retryable=False
        Outcome("skipped", "chưa hỗ trợ"),
    ],
)
def test_never_retries_non_retryable_outcomes(outcome: Outcome) -> None:
    sleeps: list[float] = []
    attempt = Attempts(outcome)

    assert run(attempt, sleeps) == outcome
    assert attempt.calls == 1
    assert sleeps == []


def test_needs_check_after_a_retry_is_not_retried_again() -> None:
    attempt = Attempts(RETRYABLE, Outcome("needs_check"))

    assert run(attempt, []).status == "needs_check"
    assert attempt.calls == 2


def test_session_error_propagates_without_retry() -> None:
    attempt = Attempts(SessionExpiredError("account_a", "hết hạn"), Outcome("posted"))

    with pytest.raises(SessionExpiredError):
        run(attempt, [])
    assert attempt.calls == 1


def test_single_attempt_means_no_retry() -> None:
    attempt = Attempts(RETRYABLE)

    assert run(attempt, [], attempts=1).message == "mạng chập chờn (đã thử 1 lần)"
    assert attempt.calls == 1


def test_zero_attempts_rejected() -> None:
    with pytest.raises(ValueError):
        run(Attempts(), [], attempts=0)
