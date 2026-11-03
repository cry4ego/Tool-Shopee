"""Test lưu trạng thái tác vụ (chống đăng trùng)."""
import json
from pathlib import Path

import pytest

from state_store import StateError, StateStore, state_path_for

pytestmark = pytest.mark.unit


def test_record_and_get_in_memory() -> None:
    store = StateStore(None)

    store.record("t001", "posted", "account_a", "ok")

    assert store.get_status("t001") == "posted"
    assert store.get_status("t999") is None


@pytest.mark.parametrize(
    ("status", "done"),
    [
        ("posted", True),
        ("needs_check", True),
        ("missed", True),
        ("failed", False),
        ("skipped", False),
        ("dry_run", False),
    ],
)
def test_is_done(status: str, done: bool) -> None:
    store = StateStore(None)
    store.record("t001", status, "account_a")

    assert store.is_done("t001") is done


def test_unknown_task_is_not_done() -> None:
    assert StateStore(None).is_done("t001") is False


def test_invalid_status_rejected() -> None:
    with pytest.raises(ValueError, match="không hợp lệ"):
        StateStore(None).record("t001", "done", "account_a")


def test_persists_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "state" / "plan.state.json"
    StateStore(path).record("t001", "posted", "account_a", "Đã đăng")

    reloaded = StateStore(path)

    assert reloaded.get_status("t001") == "posted"
    entry = json.loads(path.read_text(encoding="utf-8"))["tasks"]["t001"]
    assert entry["account"] == "account_a"
    assert entry["message"] == "Đã đăng"
    assert entry["updated_at"]


def test_save_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "plan.state.json"
    StateStore(path).record("t001", "posted", "account_a")

    assert [p.name for p in tmp_path.iterdir()] == ["plan.state.json"]


@pytest.mark.parametrize("content", ["{ hỏng", '{"khong_phai_tasks": {}}', "[]"])
def test_corrupt_file_raises_instead_of_overwriting(tmp_path: Path, content: str) -> None:
    path = tmp_path / "plan.state.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(StateError, match="File state hỏng"):
        StateStore(path)
    assert path.read_text(encoding="utf-8") == content


def test_state_path_is_named_after_plan(tmp_path: Path) -> None:
    assert state_path_for("plans/thang11.json", tmp_path) == tmp_path / "thang11.state.json"
