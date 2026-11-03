Dựa trên yêu cầu của bạn, tôi sẽ xây dựng cho bạn một bộ mã cơ sở (base code) hoàn chỉnh có thể chạy được, sử dụng Python + Playwright + Chrome thực tế. Thiết kế cốt lõi như sau: không tự động hóa đăng nhập, mà sử dụng cơ chế storage_state để lưu và tái sử dụng trạng thái đăng nhập, đồng thời cô lập phiên của từng tài khoản thông qua các BrowserContext độc lập, đạt được mục tiêu luân phiên đa tài khoản .

1. Cấu trúc thư mục dự án
text
shopee-video-tool/
├── accounts/
│   ├── account_a.json      # storage_state của tài khoản A
│   └── account_b.json
├── videos/
│   └── sample.mp4
├── config.py               # Cấu hình
├── login.py                # Đăng nhập thủ công, lưu trạng thái
├── poster.py               # Logic đăng video
├── scheduler.py            # Luân phiên + Lên lịch
└── requirements.txt
2. Cài đặt phụ thuộc
txt
# requirements.txt
playwright>=1.40.0
Sau khi cài đặt, chạy playwright install chrome để đảm bảo Playwright có thể điều khiển Chrome thực tế (hoặc sử dụng trực tiếp Chrome đã cài trên máy).

3. Cấu hình config.py
python
# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_DIR = os.path.join(BASE_DIR, "accounts")
VIDEOS_DIR = os.path.join(BASE_DIR, "videos")

# URL gốc trang người bán Shopee (điều chỉnh theo khu vực)
SHOPEE_SELLER_URL = "https://banhang.shopee.vn"

# Đường dẫn trang Video (theo giao diện Seller Centre)
SHOPEE_VIDEO_URL = f"{SHOPEE_SELLER_URL}/marketing/live-video/video"

os.makedirs(ACCOUNTS_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)
4. Đăng nhập thủ công, lưu trạng thái login.py
Điểm mấu chốt: bạn tự đăng nhập thủ công một lần, script chỉ chịu trách nhiệm lưu cookie và localStorage sau khi đăng nhập .

python
# login.py
from playwright.sync_api import sync_playwright
from config import ACCOUNTS_DIR, SHOPEE_SELLER_URL
import os

def login_and_save(account_name: str):
    """
    Mở trình duyệt, chờ người dùng đăng nhập thủ công, sau đó lưu trạng thái.
    account_name: tên tài khoản, ví dụ "account_a"
    """
    state_path = os.path.join(ACCOUNTS_DIR, f"{account_name}.json")
    
    with sync_playwright() as p:
        # Sử dụng Chrome thực tế, không dùng Chromium đi kèm
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context()
        page = context.new_page()
        
        page.goto(SHOPEE_SELLER_URL)
        
        print(f"[{account_name}] Vui lòng đăng nhập Shopee Seller Centre trong trình duyệt...")
        print("Sau khi đăng nhập thành công, nhấn Enter tại đây để lưu trạng thái.")
        input()
        
        # Lưu cookies + localStorage
        context.storage_state(path=state_path)
        print(f"Đã lưu trạng thái vào: {state_path}")
        
        browser.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        login_and_save(sys.argv[1])
    else:
        login_and_save("account_a")
Cách sử dụng:

bash
python login.py account_a
python login.py account_b
5. Logic đăng video cốt lõi poster.py
Phần này điều khiển giao diện web. Dựa trên mô tả trong tài liệu chính thức của Shopee, quy trình đăng video trên Seller Centre là: vào Live & Video → tải video lên → điền caption → (tùy chọn) đặt lịch → đăng . Dưới đây là triển khai dựa trên selector phổ biến; bạn cần điều chỉnh selector thực tế theo giao diện phiên bản ngôn ngữ khu vực của mình.

python
# poster.py
from playwright.sync_api import sync_playwright, Page
from config import ACCOUNTS_DIR, SHOPEE_VIDEO_URL
import os

def post_video_for_account(
    account_name: str,
    video_path: str,
    caption: str = "",
    schedule_time: str = None,  # Định dạng: "2026-11-03 14:00"
    headless: bool = False
):
    """
    Sử dụng trạng thái đã lưu của tài khoản chỉ định để đăng một video.
    Trả về True/False cho biết thành công hay không.
    """
    state_path = os.path.join(ACCOUNTS_DIR, f"{account_name}.json")
    if not os.path.exists(state_path):
        raise FileNotFoundError(f"Không tìm thấy trạng thái đăng nhập: {state_path}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        # Tạo context độc lập, tải trạng thái đăng nhập
        context = browser.new_context(storage_state=state_path)
        page = context.new_page()
        
        try:
            page.goto(SHOPEE_VIDEO_URL, wait_until="networkidle")
            page.wait_for_timeout(3000)
            
            # === Bước 1: Nhấp nút "Tải video lên" ===
            # Selector cần điều chỉnh theo giao diện thực tế
            upload_btn = page.locator('button:has-text("Tải video lên"), button:has-text("Upload Video")').first
            upload_btn.wait_for(timeout=15000)
            upload_btn.click()
            page.wait_for_timeout(2000)
            
            # === Bước 2: Tải tệp video lên ===
            # Tìm input file (thường ẩn, cần dùng set_input_files)
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(video_path)
            print(f"[{account_name}] Đã chọn tệp: {video_path}")
            
            # Chờ tải lên hoàn tất (điều chỉnh theo kích thước video)
            page.wait_for_timeout(10000)
            
            # === Bước 3: Điền caption ===
            # Shopee có thể sử dụng contenteditable hoặc textarea
            caption_input = page.locator(
                'textarea[placeholder*="caption" i], '
                'div[contenteditable="true"]'
            ).first
            if caption_input.count() > 0:
                caption_input.fill(caption)
                print(f"[{account_name}] Đã điền caption: {caption[:30]}...")
            
            # === Bước 4: Đặt lịch đăng (tùy chọn) ===
            if schedule_time:
                # Nhấp "Lên lịch đăng bài sau"
                schedule_toggle = page.locator(
                    'text="Lên lịch đăng bài sau", text="Schedule To Post Later"'
                ).first
                if schedule_toggle.count() > 0:
                    schedule_toggle.click()
                    page.wait_for_timeout(1000)
                    # Điền thời gian (định dạng tùy thuộc vào component thời gian của Shopee)
                    # Đây là placeholder, cần điều chỉnh theo giao diện thực tế
                    print(f"[{account_name}] Đặt lịch đăng: {schedule_time}")
                    # page.fill('input[type="datetime-local"]', schedule_time)
            
            # === Bước 5: Đồng ý điều khoản và đăng ===
            tos_checkbox = page.locator('input[type="checkbox"]').last
            if tos_checkbox.count() > 0:
                tos_checkbox.check()
            
            post_btn = page.locator('button:has-text("Đăng"), button:has-text("Post")').last
            post_btn.click()
            print(f"[{account_name}] Đã nhấp nút đăng, chờ xử lý...")
            
            page.wait_for_timeout(8000)
            
            # Lưu trạng thái đã cập nhật (cookie có thể được làm mới)
            context.storage_state(path=state_path)
            print(f"[{account_name}] Đăng video hoàn tất.")
            return True
            
        except Exception as e:
            print(f"[{account_name}] Đăng video thất bại: {e}")
            # Chụp ảnh màn hình để gỡ lỗi
            page.screenshot(path=f"error_{account_name}.png")
            return False
        finally:
            browser.close()
6. Luân phiên và lên lịch scheduler.py
python
# scheduler.py
import time
import random
from poster import post_video_for_account
import os
from config import VIDEOS_DIR

# Danh sách tài khoản
ACCOUNTS = ["account_a", "account_b"]

# Hàng đợi tác vụ: (đường dẫn video, caption)
TASKS = [
    (os.path.join(VIDEOS_DIR, "video1.mp4"), "Sản phẩm hot #shopee #sale"),
    (os.path.join(VIDEOS_DIR, "video2.mp4"), "Mẫu mới về #fashion #trending"),
]

def round_robin_post():
    """Luân phiên đăng video giữa các tài khoản"""
    account_idx = 0
    for i, (video_path, caption) in enumerate(TASKS):
        account = ACCOUNTS[account_idx % len(ACCOUNTS)]
        print(f"\n=== Tác vụ {i+1}/{len(TASKS)}: {account} đăng {os.path.basename(video_path)} ===")
        
        post_video_for_account(
            account_name=account,
            video_path=video_path,
            caption=caption,
            headless=False  # Khám phá khuyến nghị False để quan sát
        )
        
        account_idx += 1
        
        # Chờ ngẫu nhiên giữa các tài khoản, giảm pattern bất thường
        if i < len(TASKS) - 1:
            delay = random.randint(60, 180)
            print(f"Chờ {delay} giây trước tác vụ tiếp theo...")
            time.sleep(delay)

if __name__ == "__main__":
    round_robin_post()
7. Những điểm cần lưu ý
Giới hạn cô lập: Các BrowserContext khác nhau cô lập cookie và localStorage, nhưng chia sẻ cùng một IP và fingerprint máy . Đối với khám phá đa tài khoản trên máy cá nhân, điều này có nghĩa nếu Shopee phát hiện qua IP hoặc fingerprint, vẫn có thể liên kết được. Nếu cần cô lập thực sự, cần kết hợp proxy hoặc trình duyệt antidetect, nhưng điều đó vượt quá phạm vi "cơ sở" này.

Tự động hóa đăng nhập: Cố ý không làm. Tự động điền mật khẩu dễ kích hoạt xác minh và phong tỏa; lưu trạng thái sau khi đăng nhập thủ công là cách ổn định nhất .

Selector là điểm dễ vỡ nhất: Tất cả các locator trong poster.py đều là ước lượng dựa trên mô tả giao diện. Bạn cần chạy headless=False, quan sát giao diện thực tế, sử dụng công cụ devtools của Playwright (page.pause()) để lấy selector chính xác.

Số lượng tài khoản: Cơ sở này không giới hạn số lượng tài khoản (khác với giới hạn 3 tài khoản của LUNO ), nhưng càng nhiều tài khoản trên cùng một IP thì rủi ro càng cao.

Nếu bạn gặp vấn đề selector trong một bước cụ thể, hoặc muốn thêm chức năng tương tác chéo (xem video lẫn nhau/bình luận) vào giai đoạn sau, hãy cho tôi biết hướng đi, tôi sẽ tiếp tục mở rộng dựa trên cơ sở này.