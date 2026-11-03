"""Kiểu dữ liệu dùng chung: tài khoản, tác vụ đăng, kế hoạch."""
import re
from dataclasses import dataclass
from datetime import datetime

# Loại tác vụ hỗ trợ: đăng video (F2a) và bài đăng (F2b)
TASK_TYPES = ("video", "post")

# Tên tài khoản được dùng làm tên file accounts/<name>.json → chỉ cho phép ký tự an toàn
ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class AccountProfile:
    """Cấu hình riêng của một tài khoản trong file kế hoạch."""

    name: str
    hashtags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Task:
    """Một mục cần đăng. Đường dẫn file đã được chuyển thành đường dẫn tuyệt đối."""

    id: str
    type: str
    account: str
    caption: str = ""
    hashtags: tuple[str, ...] = ()
    video_path: str | None = None
    images: tuple[str, ...] = ()
    schedule_time: datetime | None = None
    product_id: str | None = None


@dataclass(frozen=True)
class Plan:
    """File kế hoạch sau khi đọc và kiểm tra hợp lệ."""

    accounts: dict[str, AccountProfile]
    tasks: tuple[Task, ...]
