"""Cấu hình logging: ghi ra file UTF-8 (xoay vòng) và ra console.

Gọi setup_logging() một lần ở đầu mỗi entry point (login.py, scheduler.py).
Các module khác chỉ cần: logger = logging.getLogger(__name__)
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOG_BACKUP_COUNT, LOG_FILE, LOG_LEVEL, LOG_MAX_BYTES

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# Đánh dấu handler do module này gắn, để gọi lại setup_logging() không bị nhân đôi log
_OWNED_ATTR = "_shopee_tool_owned"


def _force_utf8_console() -> None:
    """Tránh UnicodeEncodeError khi output bị chuyển hướng và Windows dùng bảng mã cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def setup_logging(log_file: str | Path = LOG_FILE, level: str | int = LOG_LEVEL) -> None:
    """Gắn handler ghi file (UTF-8, xoay vòng) và handler console vào root logger."""
    _force_utf8_console()

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _OWNED_ATTR, False)]:
        root.removeHandler(handler)
        handler.close()

    file_handler = RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    console_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(LOG_FORMAT)
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        setattr(handler, _OWNED_ATTR, True)
        root.addHandler(handler)
    root.setLevel(level)
