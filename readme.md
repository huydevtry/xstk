# ⚽ Football Betting Realtime Engine (Learning Project)

Dự án học tập xây dựng một hệ thống backend tính điểm dự đoán tỉ số bóng đá theo thời gian thực (Real-time). Dự án sử dụng mô hình kiến trúc Zero Trust Architecture, ủy quyền toàn bộ việc định danh người dùng cho Cloudflare Access.

## 🛠 Tech Stack

* **Backend Framework:** FastAPI (Python)
* **Database:** PostgreSQL
* **ORM:** SQLAlchemy (Async) + asyncpg
* **Authentication & Gateway:** Cloudflare Tunnel + Cloudflare Access (Zero Trust)

---

## 📋 Yêu cầu hệ thống (Prerequisites)

Trước khi cài đặt, đảm bảo máy của bạn đã có sẵn các công cụ sau:
* [Python 3.9+](https://www.python.org/downloads/)
* [PostgreSQL](https://www.postgresql.org/download/) (Đang chạy local hoặc trên server/docker)
* [Cloudflared CLI](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)

---

## 🚀 Hướng dẫn Cài đặt & Chạy Local

### Bước 1: Khởi tạo Database PostgreSQL
Tạo một database trống trong PostgreSQL để ứng dụng kết nối:
```sql
CREATE DATABASE betting_db;