# XSTK - Football Prediction Community

Ứng dụng web nhỏ để tổ chức dự đoán kết quả bóng đá theo điểm nội bộ. Người dùng có thể đặt điểm cho trận đấu, xem bảng xếp hạng, theo dõi lịch sử điểm, chia sẻ cảm nghĩ sau trận và tương tác trong feed cộng đồng.

> Dự án phục vụ học tập, thử nghiệm và giải trí nội bộ. Không dùng cho cá cược tiền thật hoặc các hoạt động trái pháp luật.

## Tính Năng Chính

- Xem danh sách trận sắp diễn ra, đang diễn ra và đã kết thúc.
- Dự đoán đội nhà, hòa hoặc đội khách bằng điểm trong tài khoản.
- Tự tính thưởng, hoàn điểm hoặc thua điểm khi admin chốt kết quả.
- Trang cá nhân với avatar, tên hiển thị, lịch sử cược, lịch sử điểm và dòng thời gian.
- Chia sẻ cảm nghĩ theo trận sau khi trận có kết quả chính thức.
- Feed cộng đồng để xem bài chia sẻ của mọi người.
- Bảng xếp hạng theo điểm.
- Trang admin để quản lý người dùng, điểm, trận đấu, kết quả và cài đặt.
- Hỗ trợ gợi ý quốc gia/flag khi admin nhập đội trong lịch thi đấu.

## Công Nghệ Sử Dụng

- FastAPI
- SQLite
- SQLAlchemy async
- Jinja2 templates
- JavaScript thuần cho giao diện
- Cloudflare Access cho định danh người dùng
- Giphy API
## Cài Đặt Local

Yêu cầu:

- Python 3.9+
- `pip`

Tạo môi trường và cài thư viện:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Tạo file `.env` ở thư mục gốc:

```env
LOCAL_DEV_AUTH=true
LOCAL_DEV_EMAIL=admin@example.com
ADMIN_EMAILS=admin@example.com
APP_BASE_URL=http://127.0.0.1:8000
GIPHY_API_KEY=your_giphy_api_key
```

Chạy ứng dụng:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --reload
```

Mở trình duyệt tại:

```text
http://127.0.0.1:8000
```

Database SQLite sẽ được tạo tự động tại `betting_db.db` khi app chạy.

## Cấu Hình Môi Trường

Các biến thường dùng:

| Biến | Ý nghĩa |
| --- | --- |
| `LOCAL_DEV_AUTH` | Bật đăng nhập giả lập khi chạy local. Đặt `true` để dùng `LOCAL_DEV_EMAIL`. |
| `LOCAL_DEV_EMAIL` | Email người dùng local. Nếu email nằm trong `ADMIN_EMAILS` thì có quyền admin. |
| `ADMIN_EMAILS` hoặc `ADMIN_EMAIL` | Danh sách email admin, phân tách bằng dấu phẩy. |
| `APP_BASE_URL` | URL public của app, dùng trong thông báo admin. |
| `GIPHY_API_KEY` | API key để mở nút chọn GIF từ GIPHY trong composer. |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram, tùy chọn. |
| `TELEGRAM_ADMIN_CHAT_ID` | Chat ID nhận thông báo user mới, tùy chọn. |

Khi chạy thật sau Cloudflare Access, app đọc email từ header Cloudflare. Người dùng mới sẽ ở trạng thái chờ duyệt cho đến khi admin phê duyệt.

## Các Trang Chính

- `/` - trang dự đoán trận đấu.
- `/guest` - trang xem nhanh cho khách.
- `/guide` - hướng dẫn sử dụng.
- `/profile` - trang cá nhân.
- `/community` - feed cộng đồng.
- `/admin` - trang quản trị, chỉ dành cho admin.

## Dữ Liệu Phụ Trợ

- `data/country_code.json`: danh sách mã quốc gia dùng để sinh flag.

## Ghi Chú Vận Hành

- Với SQLite, nên chạy app bằng một worker: `--workers 1`.
- Nên đặt app sau Cloudflare Access hoặc một lớp xác thực tương đương khi dùng thật.
- Nên sao lưu `betting_db.db` định kỳ nếu dữ liệu có giá trị.
- Telegram là tùy chọn; nếu không cấu hình token/chat ID thì app vẫn chạy bình thường.
