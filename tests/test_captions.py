"""Test ghép caption + hashtag (F4)."""
import pytest

from captions import CaptionTooLongError, build_caption, normalize_hashtag
from models import AccountProfile, Task

pytestmark = pytest.mark.unit


def make_task(caption: str = "", hashtags: tuple[str, ...] = ()) -> Task:
    return Task(id="t001", type="video", account="account_a", caption=caption, hashtags=hashtags)


def make_account(hashtags: tuple[str, ...] = ()) -> AccountProfile:
    return AccountProfile(name="account_a", hashtags=hashtags)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("#Sale", "#Sale"),
        ("sale", "#sale"),
        ("  ##hot ", "#hot"),
        ("hot deal", "#hotdeal"),
        ("", None),
        ("#", None),
        ("   ", None),
    ],
)
def test_normalize_hashtag(raw: str, expected: str | None) -> None:
    assert normalize_hashtag(raw) == expected


def test_task_hashtags_come_before_account_hashtags() -> None:
    caption = build_caption(make_task("Sản phẩm hot", ("#hot",)), make_account(("#shopeevn", "#sale")))

    assert caption == "Sản phẩm hot\n#hot #shopeevn #sale"


def test_duplicates_removed_case_insensitive_keeping_first() -> None:
    caption = build_caption(make_task("", ("#Hot", "sale")), make_account(("#SALE", "#hot", "#shopeevn")))

    assert caption == "#Hot #sale #shopeevn"


def test_hashtag_already_in_caption_is_not_repeated() -> None:
    caption = build_caption(make_task("Mua ngay #Sale"), make_account(("#sale",)))

    assert caption == "Mua ngay #Sale"


def test_caption_without_hashtags_is_kept_as_is() -> None:
    assert build_caption(make_task("  Mẫu mới về  "), make_account()) == "Mẫu mới về"


def test_empty_caption_and_no_hashtags_gives_empty_string() -> None:
    assert build_caption(make_task(), make_account()) == ""


def test_too_long_caption_raises() -> None:
    with pytest.raises(CaptionTooLongError, match="vượt giới hạn 10"):
        build_caption(make_task("x" * 8, ("#abc",)), make_account(), max_length=10)


def test_caption_at_exact_limit_is_allowed() -> None:
    assert build_caption(make_task("x" * 10), make_account(), max_length=10) == "x" * 10
