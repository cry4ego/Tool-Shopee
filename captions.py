"""Ghép caption + hashtag cho từng tác vụ (F4).

Quy tắc: hashtag của tác vụ đứng trước, sau đó tới hashtag mặc định của tài khoản.
Bỏ trùng không phân biệt hoa thường, bỏ cả hashtag đã có sẵn trong caption.
"""
import re

from config import MAX_CAPTION_LENGTH
from models import AccountProfile, Task


class CaptionTooLongError(ValueError):
    """Caption sau khi ghép hashtag vượt quá giới hạn độ dài."""


def normalize_hashtag(tag: str) -> str | None:
    """Chuẩn hóa về dạng "#tu": bỏ khoảng trắng, thêm/gộp dấu #. Trả None nếu rỗng."""
    body = re.sub(r"\s+", "", tag).lstrip("#")
    return f"#{body}" if body else None


def build_caption(task: Task, account: AccountProfile, max_length: int = MAX_CAPTION_LENGTH) -> str:
    """Trả về caption cuối cùng sẽ điền lên Shopee."""
    text = task.caption.strip()
    seen = {tag.lower() for tag in re.findall(r"#[^\s#]+", text)}

    tags: list[str] = []
    for raw in (*task.hashtags, *account.hashtags):
        tag = normalize_hashtag(raw)
        if tag is not None and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)

    caption = "\n".join(part for part in (text, " ".join(tags)) if part)
    if len(caption) > max_length:
        raise CaptionTooLongError(f"Caption dài {len(caption)} ký tự, vượt giới hạn {max_length}")
    return caption
