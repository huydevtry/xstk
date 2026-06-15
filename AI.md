# Bối cảnh dự án (Project Context)
Dự án: Hệ thống cá cược dự đoán tỉ số bóng đá (Football Betting Engine).
Mục đích: Học tập và thử nghiệm kiến trúc realtime, bất đồng bộ và Zero Trust Architecture.
Đặc điểm: Cung cấp API và giao diện web mobile-first để người dùng xem lịch thi đấu và đặt cược tỉ số bằng điểm ảo.

# Tech Stack
- Backend: Python 3.9+, FastAPI
- Server: Uvicorn (CHỈ CHẠY 1 WORKER) bọc bởi Systemd trên Linux.
- Database: SQLite (sử dụng thư viện `aiosqlite` để xử lý async).
- ORM: SQLAlchemy 2.0 (AsyncSession).
- Frontend: HTML5, Vanilla JavaScript (ES6+), Tailwind CSS (qua CDN).
- Authentication: Mạng lưới Zero Trust qua Cloudflare Tunnel + Cloudflare Access.

# Quy tắc Kiến trúc & Lập trình (Architecture & Coding Rules)

## 1. Cơ sở dữ liệu (Database Rules)
- DO SỬ DỤNG SQLITE: Tuyệt đối không dùng cấu hình đa tiến trình (multi-processing/multi-workers) để tránh lỗi `database is locked` (write-lock). 
- Toàn bộ thao tác với DB phải dùng cú pháp `async/await` thông qua `AsyncSession` của SQLAlchemy.
- Sử dụng UUID (chuẩn Uuid của SQLAlchemy 2.0) cho bảng Users.

## 2. Xác thực người dùng (Authentication - Zero Trust)
- Không viết code quản lý đăng ký/đăng nhập (Auth Form, JWT nội bộ, Session).
- Mọi request vào hệ thống đã được Cloudflare Access xác thực từ vòng ngoài.
- Backend FastAPI định danh người dùng bằng cách đọc HTTP Header: `Cf-Access-Authenticated-User-Email`.
- Cơ chế Just-In-Time Provisioning: Nếu email từ header chưa tồn tại trong bảng `users`, hệ thống tự động tạo mới (Insert) và cấp 1000 điểm khởi tạo.

## 3. Giao diện (Frontend Rules)
- Thiết kế theo hướng Mobile-First (Max-width: 640px / `max-w-xl`).
- Không sử dụng các framework frontend phức tạp như React/Vue hay Node.js/npm. Chỉ dùng Vanilla JS, fetch API và Tailwind CSS qua thẻ `<script src="https://cdn.tailwindcss.com"></script>`.
- Phân tách code rõ ràng: Giao diện nằm ở `templates/index.html`, logic tải API nằm ở `static/js/app.js`, style bổ sung nằm ở `static/css/style.css`.
- Các danh sách dữ liệu dài (như lịch thi đấu) cần dùng cơ chế gom nhóm (Group by Date) và giao diện Accordion (Mở rộng/Thu gọn) để tối ưu không gian cuộn.

## 4. Lược đồ Database (Database Schema Reference)
- `users`: id (UUID), email (String, unique), total_points (Int), created_at (DateTime).
- `matches`: id (Int), home_team (String), away_team (String), home_score (Int), away_score (Int), handicap (Float, default=0.0), status (Enum: upcoming, live, finished), start_time (DateTime).
- `bets`: id (Int), user_id (UUID - FK), match_id (Int - FK), choice (String: HOME/DRAW/AWAY), stake (Int), points_earned (Int), created_at (DateTime).

## 5. Cơ chế đặt cược (Betting Engine)
- **Pool/Pari-mutuel**: Multiplier = total_pool / stakes_on_winning_choice. Reward = floor(stake * multiplier).
- **Handicap**: Adjusted home score = home_score + handicap. Quyết định HOME/DRAW/AWAY.
- **Refund**: Nếu winning_choice không có ai cược, hoàn trả stake cho tất cả người tham gia trận đó.
- **Giới hạn**: 1 user chỉ được cược 1 lần/trận. Match phải status=upcoming.

## 5. Style Coder
- Viết code ngắn gọn, tối ưu, ưu tiên performance.
- Cung cấp giải pháp cho Senior Developer (không cần giải thích các khái niệm lập trình cơ bản).
- Khi có lỗi, tập trung kiểm tra luồng Async và Header giả mạo.