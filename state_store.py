"""Lưu kết quả từng tác vụ ra state/<tên kế hoạch>.state.json để chạy lại không bị đăng trùng.

Trạng thái "đã xong" (không chạy lại tự động): posted, needs_check, missed.
needs_check = không chắc đã đăng hay chưa → cần người kiểm tra trên Shopee,
sau đó xóa mục đó khỏi file state nếu muốn đăng lại.
"""
import json
import os
from datetime import datetime
from pathlib import Path

from config import STATE_DIR

STATUSES = ("posted", "failed", "needs_check", "missed", "skipped", "dry_run")
DONE_STATUSES = frozenset({"posted", "needs_check", "missed"})


class StateError(RuntimeError):
    """File state hỏng — dừng lại thay vì ghi đè (ghi đè có thể gây đăng trùng)."""


def state_path_for(plan_path: str | Path, state_dir: str | Path = STATE_DIR) -> Path:
    """Mỗi file kế hoạch có một file state riêng, đặt theo tên file kế hoạch."""
    return Path(state_dir) / f"{Path(plan_path).stem}.state.json"


class StateStore:
    """Kết quả tác vụ theo id. path=None → chỉ giữ trong bộ nhớ (dùng cho --fake)."""

    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path is not None else None
        self._tasks: dict[str, dict] = {}
        if self.path is not None and self.path.exists():
            try:
                self._tasks = json.loads(self.path.read_text(encoding="utf-8"))["tasks"]
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise StateError(f"File state hỏng: {self.path} ({e}). Sửa hoặc đổi tên file rồi chạy lại.") from e

    def get_status(self, task_id: str) -> str | None:
        entry = self._tasks.get(task_id)
        return entry["status"] if entry else None

    def is_done(self, task_id: str) -> bool:
        return self.get_status(task_id) in DONE_STATUSES

    def record(self, task_id: str, status: str, account: str, message: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"Trạng thái không hợp lệ: {status!r}")
        self._tasks[task_id] = {
            "status": status,
            "account": account,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "message": message,
        }
        self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps({"tasks": self._tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)
