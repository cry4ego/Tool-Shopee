"""Fixture dùng chung cho test."""
import logging

import pytest


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Trả root logger về trạng thái cũ sau mỗi test (setup_logging() gắn handler toàn cục)."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    for handler in root.handlers[:]:
        if handler not in saved_handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(saved_level)
