"""Khóa một tiến trình (F3): login.py và scheduler.py không bao giờ chạy cùng lúc.

Dùng khóa của hệ điều hành (msvcrt trên Windows, fcntl trên Linux/macOS) nên khi
tiến trình bị tắt ngang, khóa tự được nhả — không bị kẹt file khóa cũ.
"""
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config import LOCK_FILE

if os.name == "nt":
    import msvcrt
else:
    import fcntl


# Khóa trên Windows là khóa bắt buộc: khóa một byte ở xa phía sau để PID ở đầu file vẫn đọc được
_WINDOWS_LOCK_OFFSET = 1 << 20


class LockError(RuntimeError):
    """Đã có một tiến trình khác của tool đang chạy."""


def _acquire(fh) -> None:
    if os.name == "nt":
        fh.seek(_WINDOWS_LOCK_OFFSET)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(fh) -> None:
    if os.name == "nt":
        fh.seek(_WINDOWS_LOCK_OFFSET)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fh, fcntl.LOCK_UN)


@contextmanager
def single_instance(lock_path: str | Path = LOCK_FILE) -> Iterator[None]:
    """Giữ khóa trong suốt khối with; ném LockError nếu tiến trình khác đang giữ."""
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    try:
        _acquire(fh)
    except OSError:
        fh.close()
        raise LockError(f"Tool đang chạy ở một cửa sổ khác (khóa: {path}). Chờ nó xong rồi chạy lại.") from None
    try:
        fh.truncate(0)
        fh.write(str(os.getpid()).encode("ascii"))
        fh.flush()
        yield
    finally:
        _release(fh)
        fh.close()
