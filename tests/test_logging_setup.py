"""Test cấu hình logging (GĐ0)."""
import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from logging_setup import setup_logging

pytestmark = pytest.mark.unit

PROJECT_DIR = Path(__file__).resolve().parent.parent
VIETNAMESE = "Đăng video hoàn tất: Sản phẩm hot #shopee"


def _flush_root() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_writes_vietnamese_to_file_as_utf8(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "app.log"

    setup_logging(log_file=log_file)
    logging.getLogger("poster").info(VIETNAMESE)
    _flush_root()

    content = log_file.read_text(encoding="utf-8")
    assert VIETNAMESE in content
    assert "INFO" in content
    assert "poster" in content


def test_creates_missing_log_directory(tmp_path: Path) -> None:
    log_file = tmp_path / "a" / "b" / "app.log"

    setup_logging(log_file=log_file)

    assert log_file.parent.is_dir()


def test_calling_twice_does_not_duplicate_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"

    setup_logging(log_file=log_file)
    setup_logging(log_file=log_file)
    logging.getLogger("scheduler").info("chỉ một dòng")
    _flush_root()

    assert log_file.read_text(encoding="utf-8").count("chỉ một dòng") == 1


def test_file_handler_rotates(tmp_path: Path) -> None:
    setup_logging(log_file=tmp_path / "app.log")

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes > 0
    assert handlers[0].backupCount > 0


def test_no_crash_when_output_is_redirected_as_cp1252(tmp_path: Path) -> None:
    """Tái hiện lỗi cũ: output bị chuyển hướng, Windows dùng cp1252 → in tiếng Việt bị lỗi."""
    log_file = tmp_path / "app.log"
    script = (
        "import logging\n"
        "from logging_setup import setup_logging\n"
        f"setup_logging(log_file={str(log_file)!r})\n"
        f"logging.getLogger('poster').info({VIETNAMESE!r})\n"
    )
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}

    result = subprocess.run(
        [sys.executable, "-c", script], cwd=PROJECT_DIR, env=env, capture_output=True, timeout=60
    )

    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, stderr
    assert "Logging error" not in stderr
    assert VIETNAMESE in result.stdout.decode("utf-8")
    assert VIETNAMESE in log_file.read_text(encoding="utf-8")
