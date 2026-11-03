# Kiểm thử thủ công trong VS Code

Làm lần lượt từ trên xuống. Mỗi bước ghi rõ: lệnh → kết quả mong đợi. Gặp kết quả khác thì dừng lại, chụp màn hình terminal + ảnh trong `logs\screenshots\` (nếu có).

Lệnh dưới đây chạy trong **terminal PowerShell của VS Code** (mặc định trên Windows).

---

## 0. Chuẩn bị

1. Mở thư mục dự án: `File → Open Folder… → D:\Scrip Shopee`.
2. Mở terminal: `Terminal → New Terminal` (hoặc ``Ctrl+` ``). Dòng nhắc phải là `PS D:\Scrip Shopee>`; nếu không:

   ```powershell
   cd "D:\Scrip Shopee"
   ```

3. Cài thư viện (một lần):

   ```powershell
   pip install -r requirements-dev.txt
   ```

4. Theo dõi log ở một terminal thứ hai (nút **Split Terminal** ở góc terminal), để nguyên trong suốt quá trình thử:

   ```powershell
   Get-Content logs\app.log -Tail 20 -Wait
   ```

Sau mỗi lệnh, xem mã thoát bằng:

```powershell
$LASTEXITCODE
```

`0` ổn · `1` có tác vụ lỗi / cần kiểm tra / lỡ giờ · `2` không chạy được (đang có lượt khác chạy) · `130` dừng bằng Ctrl+C.

---

## 1. Test tự động (không cần tài khoản, không vào Shopee)

```powershell
pytest -m unit
```

```powershell
pytest -m integration
```

```powershell
ruff check .
```

**Mong đợi:** tất cả `passed`, ruff `All checks passed!`. Test integration mở Chromium ẩn trên trang giả lập, mất khoảng 30 giây.

---

## 2. F1 — Đăng nhập thủ công + kiểm tra phiên

### 2.1. Đăng nhập

```powershell
python login.py account_a
```

**Mong đợi:** Chrome mở trang `banhang.shopee.vn`. Bạn **tự** đăng nhập (kể cả OTP). Khi đã vào được trang quản lý shop, quay lại terminal, nhấn **Enter**.

- Log: `Đã lưu trạng thái vào: ...\accounts\account_a.json`, mã thoát `0`.
- Thử thêm: chạy `python login.py account_thu`, rồi nhấn Enter **khi Chrome vẫn đang ở trang đăng nhập**. Log báo "vẫn ở trang đăng nhập — CHƯA lưu", mã thoát `1`, không có file `accounts\account_thu.json`.
  → Nếu nó **vẫn lưu**: `LOGIN_URL_MARKERS` trong `config.py` sai. Ghi lại URL trên thanh địa chỉ của trang đăng nhập.

### 2.2. Kiểm tra phiên

```powershell
python login.py --check
```

**Mong đợi:** Chrome mở rồi tự đóng; log `account_a   ok`, mã thoát `0`.

### 2.3. Giả lập phiên hết hạn

Tạo một tài khoản có phiên rỗng:

```powershell
Set-Content accounts\account_het_han.json '{"cookies": [], "origins": []}'
```

```powershell
python login.py --check account_het_han
```

**Mong đợi:** `account_het_han   hết hạn`, mã thoát `1`. Đây cũng là cách **xác minh `LOGIN_URL_MARKERS`**: nếu nó báo `ok` thì Shopee chuyển về một URL đăng nhập mà tool chưa biết → ghi lại URL đó.

Dọn dẹp:

```powershell
Remove-Item accounts\account_het_han.json
```

### 2.4. Tài khoản chưa đăng nhập

```powershell
python login.py --check account_z
```

**Mong đợi:** `account_z   chưa đăng nhập`, mã thoát `1`, không mở Chrome.

---

## 3. F4 — File kế hoạch, caption + hashtag

### 3.1. Chuẩn bị video và file kế hoạch

1. Chép **một video ngắn, hợp lệ để đăng** vào `videos\`, đặt tên `thu1.mp4`.
2. Tạo file `plans\thu_nghiem.json` (trong VS Code: chuột phải thư mục `plans` → New File) với nội dung dưới đây. Sửa `schedule_time` của `t003` thành **hôm nay, 5 phút sau giờ hiện tại** (xem đồng hồ góc phải màn hình), dạng `"YYYY-MM-DD HH:MM"`:

```json
{
  "accounts": {
    "account_a": { "hashtags": ["#shopeevn", "#Sale"] }
  },
  "tasks": [
    {
      "id": "t001",
      "type": "video",
      "account": "account_a",
      "video_path": "videos/thu1.mp4",
      "caption": "Video thử nghiệm #sale",
      "hashtags": ["hot", "#HOT", "#moi ve"]
    },
    {
      "id": "t002",
      "type": "post",
      "account": "account_a",
      "images": ["videos/thu1.mp4"],
      "caption": "Bài đăng thử"
    },
    {
      "id": "t003",
      "type": "video",
      "account": "account_a",
      "video_path": "videos/thu1.mp4",
      "caption": "Video hẹn giờ",
      "schedule_time": "2026-11-03 15:00"
    }
  ]
}
```

### 3.2. Kiểm tra file kế hoạch

```powershell
python scheduler.py --plan plans\thu_nghiem.json --validate
```

**Mong đợi:** `File kế hoạch hợp lệ: 1 tài khoản, 3 tác vụ`, và caption của `t001` là:

```text
'Video thử nghiệm #sale\n#hot #moive #shopeevn'
```

Kiểm tra từng điểm: `hot` được thêm `#`; `#HOT` bị bỏ vì trùng `#hot`; `#moi ve` thành `#moive`; `#Sale` của tài khoản bị bỏ vì caption đã có `#sale`.

### 3.3. Bắt lỗi trong file kế hoạch

Sửa tạm trong `plans\thu_nghiem.json`: đổi `"schedule_time"` của `t003` thành `"shedule_time"`, và đổi `"account"` của `t002` thành `"account_z"`. Chạy lại lệnh `--validate`.

**Mong đợi:** báo **cùng lúc 2 lỗi** (`khóa không hợp lệ 'shedule_time'` và `'account_z' không có trong 'accounts'`), mã thoát `1`. Sửa lại như cũ trước khi sang bước sau.

---

## 4. F3 + F5 — Chạy thử không mở trình duyệt (`--fake`)

```powershell
python scheduler.py --plan plans\thu_nghiem.json --fake
```

**Mong đợi** (khi `t003` chưa đến giờ):

- `[t003] Chưa đến giờ (...)`.
- `[fake] account_a đăng video t001 ...`, rồi `[fake] Bỏ qua chờ N giây` (N từ 60 đến 180), rồi `t002`.
- Ở chế độ fake, cả video lẫn bài đăng đều ra `dry_run`.
- Không tạo file `state\thu_nghiem.state.json`.

Chờ quá giờ hẹn của `t003` rồi chạy lại lệnh trên → lần này `t003` cũng được "đăng".

---

## 5. F3 — Khóa: không bao giờ chạy 2 tài khoản cùng lúc

1. Terminal 1:

   ```powershell
   python login.py account_b
   ```

   Chrome mở và **để nguyên**, đừng nhấn Enter.
2. Terminal 2 (Split Terminal):

   ```powershell
   python scheduler.py --plan plans\thu_nghiem.json --fake
   ```

   **Mong đợi:** `Tool đang chạy ở một cửa sổ khác (khóa: ...run.lock)`, mã thoát `2`.
3. Quay lại terminal 1, nhấn **Ctrl+C** (có thể hiện traceback — bình thường). Chạy lại lệnh ở terminal 2 → lần này chạy bình thường.

---

## 6. F2 — Chạy qua giao diện Shopee thật, KHÔNG bấm Đăng (`--dry-run`)

```powershell
python scheduler.py --plan plans\thu_nghiem.json --dry-run
```

**Quan sát Chrome**, đúng thứ tự:

1. Mở Seller Centre, chờ khoảng 5 giây (kiểm tra phiên) → mở trang Video.
2. Bấm "Tải video lên" → video được chọn **mà không hiện hộp thoại chọn file của Windows**.
3. Chờ tải lên xong → điền caption → tick "đồng ý điều khoản".
4. **Dừng, không bấm Đăng**, Chrome đóng. Log: `[dry-run] Đã điền xong mọi bước, KHÔNG bấm Đăng`.

Rất có thể một bước nào đó lỗi, vì selector chưa từng được thử trên Shopee thật. Khi đó:

- Log ghi `Lỗi TRƯỚC khi bấm Đăng` và tool tự thử lại (chờ 30 giây, rồi 60 giây — tổng cộng vài phút).
- Mở `logs\screenshots\` → file `.png` cho biết trang đang ở đâu, file `.html` để lấy selector.
- Gửi lại: dòng lỗi trong log + ảnh `.png` + URL trang Video thật.

`t002` (bài đăng) sẽ là `skipped` — chưa hỗ trợ (GĐ6).

Thử **Ctrl+C** khi Chrome đang tải video lên → mã thoát `130`, Chrome đóng, không có file state.

---

## 7. F2 — Đăng thật (chỉ khi bước 6 đã chạy trọn vẹn)

> ⚠️ Bước này đăng video thật lên shop.

```powershell
python scheduler.py --plan plans\thu_nghiem.json
```

**Mong đợi:** log `Shopee báo đăng thành công`; video xuất hiện trong mục Video của shop. Xem kết quả đã lưu:

```powershell
Get-Content state\thu_nghiem.state.json
```

`t001` là `"posted"`. Chạy lại đúng lệnh đăng thật một lần nữa → log `Bỏ qua vì đã xong từ trước: t001`, **không đăng lại**.

Nếu kết quả là `needs_check` (đã bấm Đăng nhưng không thấy thông báo): kiểm tra trên Shopee, rồi báo lại chữ thông báo thành công thật của Shopee để sửa `SUCCESS_TEXTS` trong `ui_selectors.py`.

---

## 8. F5 — Lỡ giờ (`missed`)

Thêm vào `tasks` trong `plans\thu_nghiem.json` một tác vụ có `schedule_time` là **hôm nay, 3 tiếng trước giờ hiện tại** (ví dụ bây giờ 14:30 thì ghi `11:30`):

```json
{ "id": "t004", "type": "video", "account": "account_a",
  "video_path": "videos/thu1.mp4", "schedule_time": "2026-11-03 11:30" }
```

```powershell
python scheduler.py --plan plans\thu_nghiem.json --fake
```

**Mong đợi:** `[t004] Kết quả: missed Trễ ... phút so với giờ hẹn ...`, mã thoát `1`. Thử thêm: đặt 1 tiếng trước (trong khoảng cho phép 120 phút) → `t004` được "đăng" bình thường. Ở chế độ thật, tác vụ đã `missed` sẽ không bao giờ được đăng nữa.

---

## 9. F5 — Windows Task Scheduler

Đăng ký ở chế độ thử (không bấm Đăng):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Plan plans\thu_nghiem.json -DryRun
```

**Mong đợi:** `Registered 'ShopeeVideoPoster': every 15 minute(s) ... (dry-run)`. Mở **Task Scheduler** (gõ trong Start) → Task Scheduler Library → `ShopeeVideoPoster`: Trigger lặp mỗi 15 phút, tab Settings có "Do not start a new instance".

Khoảng 1 phút sau, Chrome tự mở và chạy như bước 6; theo dõi log ở terminal 2. Cột **Last Run Result** cho biết mã thoát.

Chế độ dry-run không ghi state nên **cứ 15 phút Chrome lại mở một lần** — xem một lượt xong thì gỡ:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Remove
```

---

## 10. Dọn dẹp sau khi thử

- Xóa file kết quả để thử lại từ đầu: `Remove-Item state\thu_nghiem.state.json`
- Bỏ một tài khoản khỏi tool: xóa file `accounts\<tên>.json` tương ứng.
- Log và ảnh lỗi: thư mục `logs\` (đã nằm trong `.gitignore`).

## Bảng ghi kết quả

| Bước | Chức năng | Đạt / Lỗi | Ghi chú (dòng log, URL, ảnh) |
|------|-----------|-----------|------------------------------|
| 1 | Test tự động | | |
| 2.1 | Đăng nhập + lưu phiên | | |
| 2.2 | `--check` ok | | |
| 2.3 | Phát hiện hết hạn | | |
| 3.2 | Caption + hashtag | | |
| 3.3 | Báo nhiều lỗi một lần | | |
| 4 | `--fake`, chưa đến giờ | | |
| 5 | Khóa một tiến trình | | |
| 6 | `--dry-run` trên Shopee thật | | |
| 7 | Đăng thật + không đăng lại | | |
| 8 | `missed` | | |
| 9 | Task Scheduler | | |
