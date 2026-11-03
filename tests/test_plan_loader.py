"""Test đọc và kiểm tra file kế hoạch (F5 - dữ liệu)."""
import copy
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from plan_loader import PlanError, load_plan

pytestmark = pytest.mark.unit

VALID_PLAN: dict = {
    "accounts": {
        "account_a": {"hashtags": ["#shopeevn"]},
        "account_b": {},
    },
    "tasks": [
        {
            "id": "t001",
            "type": "video",
            "account": "account_a",
            "video_path": "videos/v1.mp4",
            "caption": "Sản phẩm hot",
            "hashtags": ["#hot"],
            "schedule_time": "2026-11-03 14:00",
            "product_id": None,
        },
        {
            "id": "t002",
            "type": "post",
            "account": "account_b",
            "images": ["images/p1.jpg"],
            "caption": "Mẫu mới về",
        },
    ],
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Thư mục dự án giả: 2 tài khoản đã đăng nhập, 1 video, 1 ảnh."""
    (tmp_path / "accounts").mkdir()
    for name in ("account_a", "account_b"):
        (tmp_path / "accounts" / f"{name}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "v1.mp4").write_bytes(b"fake")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "p1.jpg").write_bytes(b"fake")
    return tmp_path


def load(project: Path, data: dict):
    path = project / "plan.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_plan(path, base_dir=project, accounts_dir=project / "accounts")


def errors_of(project: Path, mutate: Callable[[dict], object]) -> list[str]:
    data = copy.deepcopy(VALID_PLAN)
    mutate(data)
    with pytest.raises(PlanError) as exc_info:
        load(project, data)
    return exc_info.value.errors


def test_loads_valid_plan(project: Path) -> None:
    plan = load(project, VALID_PLAN)

    video, post = plan.tasks
    assert video.id == "t001"
    assert video.schedule_time == datetime(2026, 11, 3, 14, 0)
    assert video.hashtags == ("#hot",)
    assert Path(video.video_path).is_absolute()
    assert video.video_path.endswith("v1.mp4")
    assert post.type == "post"
    assert post.images[0].endswith("p1.jpg")
    assert post.schedule_time is None
    assert plan.accounts["account_a"].hashtags == ("#shopeevn",)
    assert plan.accounts["account_b"].hashtags == ()


def test_product_id_number_becomes_string(project: Path) -> None:
    data = copy.deepcopy(VALID_PLAN)
    data["tasks"][0]["product_id"] = 12345

    assert load(project, data).tasks[0].product_id == "12345"


def test_missing_plan_file(tmp_path: Path) -> None:
    with pytest.raises(PlanError) as exc_info:
        load_plan(tmp_path / "khong_co.json")

    assert "Không tìm thấy file kế hoạch" in exc_info.value.errors[0]


def test_invalid_json_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text('{\n  "accounts": {,\n}', encoding="utf-8")

    with pytest.raises(PlanError) as exc_info:
        load_plan(path)

    assert "JSON" in exc_info.value.errors[0]
    assert "dòng 2" in exc_info.value.errors[0]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d["tasks"][1].update(id="t001"), "id bị trùng"),
        (lambda d: d["tasks"][0].pop("id"), "thiếu 'id'"),
        (lambda d: d["tasks"][0].update(type="reel"), "'type' phải là một trong"),
        (lambda d: d["tasks"][0].update(account="account_z"), "'account_z' không có trong 'accounts'"),
        (lambda d: d["tasks"][0].update(video_path="videos/khong_co.mp4"), "không tìm thấy file videos/khong_co.mp4"),
        (lambda d: d["tasks"][0].pop("video_path"), "video_path: thiếu đường dẫn file"),
        (lambda d: d["tasks"][0].update(images=["images/p1.jpg"]), "tác vụ video không dùng 'images'"),
        (lambda d: d["tasks"][1].pop("images"), "bài đăng cần ít nhất một ảnh"),
        (lambda d: d["tasks"][1].update(images=["images/khong_co.jpg"]), "images[0]: không tìm thấy file"),
        (lambda d: d["tasks"][0].update(schedule_time="03/11/2026 14h"), "'YYYY-MM-DD HH:MM'"),
        (lambda d: d["tasks"][0].update(schedule_time=20261103), "'YYYY-MM-DD HH:MM'"),
        (lambda d: d["tasks"][0].update(shedule_time="2026-11-03 14:00"), "khóa không hợp lệ 'shedule_time'"),
        (lambda d: d["tasks"][0].update(hashtags="#hot"), "hashtags: phải là danh sách chuỗi"),
        (lambda d: d["tasks"][0].update(caption=123), "caption: phải là chuỗi"),
        (lambda d: d["tasks"][0].update(product_id=True), "product_id: phải là chuỗi, số hoặc null"),
        (lambda d: d["tasks"][0].update(caption="x" * 600), "vượt giới hạn"),
        (lambda d: d["accounts"].update({"../evil": {}}), "tên tài khoản chỉ được chứa"),
        (lambda d: d["accounts"].update(account_c={}), "chạy: python login.py account_c"),
        (lambda d: d["accounts"]["account_a"].update(tags=[]), "khóa không hợp lệ 'tags'"),
        (lambda d: d.update(accounts={}), "'accounts' phải là object"),
        (lambda d: d.update(tasks={}), "'tasks' phải là danh sách"),
        (lambda d: d.update(task=[]), "khóa không hợp lệ 'task'"),
    ],
)
def test_reports_invalid_field(project: Path, mutate: Callable[[dict], object], expected: str) -> None:
    errors = errors_of(project, mutate)

    assert any(expected in error for error in errors), errors


def test_error_mentions_task_id(project: Path) -> None:
    errors = errors_of(project, lambda d: d["tasks"][1].update(type="reel"))

    assert errors == ["tasks[1] (id=t002): 'type' phải là một trong ('video', 'post'), nhận 'reel'"]


def test_collects_all_errors_at_once(project: Path) -> None:
    def break_three_things(data: dict) -> None:
        data["tasks"][0]["schedule_time"] = "sai"
        data["tasks"][1]["account"] = "account_z"
        data["accounts"]["account_c"] = {}

    errors = errors_of(project, break_three_things)

    assert len(errors) == 3
    assert any("schedule_time" in e for e in errors)
    assert any("account_z" in e for e in errors)
    assert any("account_c" in e for e in errors)


def test_plan_root_must_be_object(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(PlanError, match="1 lỗi"):
        load_plan(path)
