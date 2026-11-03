"""Hằng số cấu hình: đường dẫn thư mục, URL Shopee Seller Centre và logging."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_DIR = os.path.join(BASE_DIR, "accounts")
VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(LOGS_DIR, "screenshots")
PLANS_DIR = os.path.join(BASE_DIR, "plans")
STATE_DIR = os.path.join(BASE_DIR, "state")

# Khóa dùng chung cho login.py và scheduler.py: không bao giờ mở 2 tài khoản cùng lúc
LOCK_FILE = os.path.join(STATE_DIR, "run.lock")

# Thời gian chờ ngẫu nhiên (giây) giữa hai tác vụ liên tiếp
TASK_DELAY_RANGE = (60, 180)

# Lên lịch (F5): schedule_time hiểu theo giờ của máy. Tác vụ trễ quá số phút này
# (máy tắt/ngủ lúc đến giờ) bị đánh dấu "missed" thay vì đăng muộn.
LATE_GRACE_MINUTES = 120

# URL gốc trang người bán Shopee (điều chỉnh theo khu vực)
SHOPEE_SELLER_URL = "https://banhang.shopee.vn"

# Đường dẫn trang Video (theo giao diện Seller Centre)
SHOPEE_VIDEO_URL = f"{SHOPEE_SELLER_URL}/marketing/live-video/video"

# Dấu hiệu URL trang đăng nhập: bị chuyển về đây nghĩa là phiên hết hạn.
# CHƯA xác minh với Shopee — mở Seller Centre khi đã đăng xuất để xem URL thật rồi chỉnh.
LOGIN_URL_MARKERS = ("/account/signin", "/buyer/login", "/login")
# Thời gian chờ xem trang có tự chuyển về trang đăng nhập không (mili giây)
SESSION_CHECK_TIMEOUT_MS = 5000

# Thời gian chờ khi đăng (mili giây)
PAGE_TIMEOUT_MS = 15_000  # chờ phần tử trên trang xuất hiện
UPLOAD_TIMEOUT_MS = 600_000  # chờ tải video lên xong (video lớn, mạng chậm)
RESULT_TIMEOUT_MS = 30_000  # chờ thông báo thành công/thất bại sau khi bấm Đăng

# Retry khi lỗi TRƯỚC khi bấm Đăng: số lần thử tối đa, thời gian chờ lần đầu (giây, nhân đôi mỗi lần)
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 30

# Độ dài tối đa của caption (kể cả hashtag). CHƯA xác minh với Shopee — chỉnh theo giới hạn thực tế.
MAX_CAPTION_LENGTH = 500

# Logging: file UTF-8, xoay vòng khi đạt LOG_MAX_BYTES, giữ LOG_BACKUP_COUNT file cũ
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
LOG_LEVEL = "INFO"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5

os.makedirs(ACCOUNTS_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)
