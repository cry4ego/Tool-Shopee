"""Đọc và kiểm tra file kế hoạch đăng bài (JSON).

Mọi lỗi được gom lại và báo một lần qua PlanError.errors, để sửa hết trong một lượt.
Schema: xem README mục 7.3 và plans/plan.example.json.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from captions import CaptionTooLongError, build_caption
from config import ACCOUNTS_DIR, BASE_DIR
from models import ACCOUNT_NAME_RE, TASK_TYPES, AccountProfile, Plan, Task

SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"

PLAN_KEYS = {"accounts", "tasks"}
ACCOUNT_KEYS = {"hashtags"}
TASK_KEYS = {"id", "type", "account", "caption", "hashtags", "video_path", "images", "schedule_time", "product_id"}


class PlanError(Exception):
    """File kế hoạch không đọc được hoặc không hợp lệ. Danh sách lỗi nằm trong .errors."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"File kế hoạch có {len(errors)} lỗi")
        self.errors = errors


def load_plan(
    path: str | Path,
    base_dir: str | Path = BASE_DIR,
    accounts_dir: str | Path = ACCOUNTS_DIR,
) -> Plan:
    """Đọc file kế hoạch. Đường dẫn file media tương đối được tính từ base_dir."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PlanError([f"Không tìm thấy file kế hoạch: {path}"]) from None
    except json.JSONDecodeError as e:
        raise PlanError([f"File kế hoạch không phải JSON hợp lệ (dòng {e.lineno}, cột {e.colno}): {e.msg}"]) from None

    if not isinstance(raw, dict):
        raise PlanError(["File kế hoạch phải là một object JSON có 'accounts' và 'tasks'"])

    errors: list[str] = []
    _check_unknown_keys(raw, PLAN_KEYS, "file kế hoạch", errors)
    accounts = _parse_accounts(raw.get("accounts"), Path(accounts_dir), errors)
    tasks = _parse_tasks(raw.get("tasks"), accounts, Path(base_dir), errors)

    if errors:
        raise PlanError(errors)
    return Plan(accounts=accounts, tasks=tuple(tasks))


def _parse_accounts(value: Any, accounts_dir: Path, errors: list[str]) -> dict[str, AccountProfile]:
    if not isinstance(value, dict) or not value:
        errors.append("'accounts' phải là object và có ít nhất một tài khoản")
        return {}

    accounts: dict[str, AccountProfile] = {}
    for name, cfg in value.items():
        where = f"accounts.{name}"
        if not ACCOUNT_NAME_RE.match(name):
            errors.append(f"{where}: tên tài khoản chỉ được chứa chữ, số, '_' và '-'")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"{where}: phải là object")
            continue
        _check_unknown_keys(cfg, ACCOUNT_KEYS, where, errors)
        hashtags = _string_list(cfg.get("hashtags", []), f"{where}.hashtags", errors)
        if not (accounts_dir / f"{name}.json").is_file():
            errors.append(f"{where}: chưa có trạng thái đăng nhập — chạy: python login.py {name}")
        accounts[name] = AccountProfile(name=name, hashtags=hashtags)
    return accounts


def _parse_tasks(
    value: Any, accounts: dict[str, AccountProfile], base_dir: Path, errors: list[str]
) -> list[Task]:
    if not isinstance(value, list):
        errors.append("'tasks' phải là danh sách")
        return []

    tasks: list[Task] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        task = _parse_task(item, index, accounts, base_dir, seen_ids, errors)
        if task is not None:
            tasks.append(task)
    return tasks


def _parse_task(
    item: Any,
    index: int,
    accounts: dict[str, AccountProfile],
    base_dir: Path,
    seen_ids: set[str],
    errors: list[str],
) -> Task | None:
    errors_before = len(errors)
    where = f"tasks[{index}]"
    if not isinstance(item, dict):
        errors.append(f"{where}: phải là object")
        return None

    task_id = item.get("id")
    if isinstance(task_id, str) and task_id.strip():
        where = f"{where} (id={task_id})"
        if task_id in seen_ids:
            errors.append(f"{where}: id bị trùng")
        seen_ids.add(task_id)
    else:
        errors.append(f"{where}: thiếu 'id' (chuỗi không rỗng)")

    _check_unknown_keys(item, TASK_KEYS, where, errors)

    task_type = item.get("type")
    if task_type not in TASK_TYPES:
        errors.append(f"{where}: 'type' phải là một trong {TASK_TYPES}, nhận {task_type!r}")

    account = item.get("account")
    if account not in accounts:
        errors.append(f"{where}: tài khoản {account!r} không có trong 'accounts'")

    caption = item.get("caption", "")
    if not isinstance(caption, str):
        errors.append(f"{where}.caption: phải là chuỗi")
        caption = ""
    hashtags = _string_list(item.get("hashtags", []), f"{where}.hashtags", errors)

    video_path: str | None = None
    images: tuple[str, ...] = ()
    if task_type == "video":
        video_path = _resolve_file(item.get("video_path"), base_dir, f"{where}.video_path", errors)
        if "images" in item:
            errors.append(f"{where}: tác vụ video không dùng 'images'")
    elif task_type == "post":
        images = _resolve_images(item.get("images"), base_dir, f"{where}.images", errors)
        if "video_path" in item:
            errors.append(f"{where}: bài đăng không dùng 'video_path'")

    schedule_time = _parse_schedule_time(item.get("schedule_time"), f"{where}.schedule_time", errors)
    product_id = _parse_product_id(item.get("product_id"), f"{where}.product_id", errors)

    if len(errors) > errors_before:
        return None

    task = Task(
        id=task_id,
        type=task_type,
        account=account,
        caption=caption,
        hashtags=hashtags,
        video_path=video_path,
        images=images,
        schedule_time=schedule_time,
        product_id=product_id,
    )
    try:
        build_caption(task, accounts[account])
    except CaptionTooLongError as e:
        errors.append(f"{where}: {e}")
        return None
    return task


def _check_unknown_keys(item: dict, allowed: set[str], where: str, errors: list[str]) -> None:
    for key in sorted(set(item) - allowed):
        errors.append(f"{where}: khóa không hợp lệ {key!r} (gõ nhầm?)")


def _string_list(value: Any, where: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errors.append(f"{where}: phải là danh sách chuỗi")
        return ()
    return tuple(value)


def _resolve_file(value: Any, base_dir: Path, where: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: thiếu đường dẫn file")
        return None
    path = Path(value) if os.path.isabs(value) else base_dir / value
    if not path.is_file():
        errors.append(f"{where}: không tìm thấy file {value}")
        return None
    return str(path.resolve())


def _resolve_images(value: Any, base_dir: Path, where: str, errors: list[str]) -> tuple[str, ...]:
    if not value:
        errors.append(f"{where}: bài đăng cần ít nhất một ảnh")
        return ()
    resolved = [
        _resolve_file(image, base_dir, f"{where}[{i}]", errors)
        for i, image in enumerate(_string_list(value, where, errors))
    ]
    return tuple(path for path in resolved if path is not None)


def _parse_schedule_time(value: Any, where: str, errors: list[str]) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, SCHEDULE_FORMAT)
    except (TypeError, ValueError):
        errors.append(f"{where}: phải có dạng 'YYYY-MM-DD HH:MM' hoặc null, nhận {value!r}")
        return None


def _parse_product_id(value: Any, where: str, errors: list[str]) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        errors.append(f"{where}: phải là chuỗi, số hoặc null")
        return None
    return str(value)
