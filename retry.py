"""Thử lại một lần đăng khi lỗi xảy ra TRƯỚC khi bấm Đăng (GĐ5).

Chỉ thử lại Outcome("failed", retryable=True). Không bao giờ thử lại:
- needs_check (có thể đã đăng → thử lại sẽ đăng trùng),
- failed do Shopee từ chối (gửi lại cùng nội dung vẫn bị từ chối),
- SessionError (phải đăng nhập lại bằng tay) — ngoại lệ được để đi tiếp lên runner.
"""
import logging
import time
from collections.abc import Callable

from config import RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS
from runner import Outcome

logger = logging.getLogger(__name__)


def retry_outcome(
    attempt: Callable[[], Outcome],
    *,
    tag: str = "",
    attempts: int = RETRY_ATTEMPTS,
    backoff_seconds: float = RETRY_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Gọi attempt() tối đa `attempts` lần; chờ backoff_seconds, 2x, 4x... giữa các lần."""
    if attempts < 1:
        raise ValueError("attempts phải >= 1")
    for number in range(1, attempts + 1):
        outcome = attempt()
        if not (outcome.status == "failed" and outcome.retryable):
            return outcome
        if number == attempts:
            logger.error("%s Vẫn lỗi sau %d lần thử: %s", tag, attempts, outcome.message)
            return Outcome(outcome.status, f"{outcome.message} (đã thử {attempts} lần)", retryable=True)

        wait = backoff_seconds * 2 ** (number - 1)
        logger.warning("%s Lần thử %d/%d lỗi trước khi bấm Đăng — thử lại sau %s giây: %s",
                       tag, number, attempts, wait, outcome.message)
        sleep(wait)
    raise AssertionError("không thể tới đây")
