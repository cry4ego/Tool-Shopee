"""Selector giao diện Shopee Seller Centre — trang đăng video.

CHƯA xác minh với giao diện thật. Cách lấy selector đúng: README mục 7.4
(chạy --dry-run với headless=False, page.pause(), "Pick locator").

Không đặt tên file là selectors.py: trùng module chuẩn `selectors` của Python
(asyncio/Playwright dùng) sẽ làm hỏng Playwright.
"""

# Nút mở hộp chọn file video (so khớp đúng toàn bộ tên nút)
UPLOAD_BUTTON_NAMES = ("Tải video lên", "Upload Video")

# Ô nhập caption: textarea có placeholder chứa "caption"/"mô tả", hoặc ô contenteditable
CAPTION_INPUT = (
    'textarea[placeholder*="caption" i], '
    'textarea[placeholder*="mô tả" i], '
    'div[contenteditable="true"]'
)

# Nhãn ô đồng ý điều khoản (checkbox thật thường bị ẩn → bấm vào nhãn)
TERMS_LABEL_PATTERN = r"đồng ý|I agree"

# Nút đăng — so khớp ĐÚNG toàn bộ tên, để không bấm nhầm "Đăng xuất", "Đăng ký..."
SUBMIT_BUTTON_NAMES = ("Đăng", "Post")

# Thông báo kết quả sau khi bấm Đăng
SUCCESS_TEXTS = ("Đăng thành công", "Posted successfully")
FAILURE_TEXTS = ("Đăng thất bại", "Failed to post")
