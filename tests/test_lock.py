"""Test khóa một tiến trình (F3)."""
import subprocess
import sys
from pathlib import Path

import pytest

from lock import LockError, single_instance

pytestmark = pytest.mark.unit

PROJECT_DIR = Path(__file__).resolve().parent.parent


def run_python(script: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", script], cwd=PROJECT_DIR, capture_output=True, timeout=60)


def try_lock_script(lock_path: Path) -> str:
    return (
        "import sys\n"
        "from lock import LockError, single_instance\n"
        "try:\n"
        f"    with single_instance({str(lock_path)!r}):\n"
        "        pass\n"
        "except LockError:\n"
        "    sys.exit(3)\n"
    )


def test_second_acquire_while_held_fails(tmp_path: Path) -> None:
    lock_path = tmp_path / "run.lock"

    with single_instance(lock_path):
        with pytest.raises(LockError, match="đang chạy"):
            with single_instance(lock_path):
                pass


def test_can_reacquire_after_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "run.lock"

    with single_instance(lock_path):
        pass
    with single_instance(lock_path):
        pass


def test_creates_parent_dir_and_writes_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"

    with single_instance(lock_path):
        assert lock_path.read_text(encoding="utf-8").strip().isdigit()


def test_other_process_is_blocked_while_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "run.lock"

    with single_instance(lock_path):
        result = run_python(try_lock_script(lock_path))

    assert result.returncode == 3, result.stderr.decode("utf-8", errors="replace")


def test_other_process_can_lock_after_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "run.lock"
    with single_instance(lock_path):
        pass

    assert run_python(try_lock_script(lock_path)).returncode == 0


def test_lock_is_freed_when_holder_process_dies(tmp_path: Path) -> None:
    """Tiến trình giữ khóa bị tắt ngang (không chạy finally) → không để lại khóa kẹt."""
    lock_path = tmp_path / "run.lock"
    killed = run_python(
        "import os\n"
        "from lock import single_instance\n"
        f"with single_instance({str(lock_path)!r}):\n"
        "    os._exit(0)\n"
    )
    assert killed.returncode == 0

    with single_instance(lock_path):
        pass
