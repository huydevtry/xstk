import csv
import sqlite3

def seed_database():
    # 1. Kết nối trực tiếp vào file SQLite
    conn = sqlite3.connect('betting_db.db')
    cursor = conn.cursor()

    success_count = 0
    
    try:
        # 2. Đọc file CSV
        with open('data/worldcup_2026_upcoming_matches.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Trích xuất các trường cần thiết, bỏ qua những cột không có trong Table (như group_name)
                match_id = int(row['id'])
                home_team = row['home_team']
                away_team = row['away_team']
                status = row['status']
                home_score = int(row['home_score'])
                away_score = int(row['away_score'])
                start_time = row['start_time_ict'] # Giữ nguyên format YYYY-MM-DD HH:MM:SS
                
                # 3. Thực thi lệnh UPSERT (Cập nhật nếu trùng ID, Thêm mới nếu chưa có)
                cursor.execute('''
                    INSERT INTO matches (id, home_team, away_team, home_score, away_score, status, start_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        home_team=excluded.home_team,
                        away_team=excluded.away_team,
                        home_score=excluded.home_score,
                        away_score=excluded.away_score,
                        status=excluded.status,
                        start_time=excluded.start_time
                ''', (match_id, home_team, away_team, home_score, away_score, status, start_time))
                
                success_count += 1

        # Lưu thay đổi vào DB
        conn.commit()
        print(f"✅ Đã cập nhật thành công {success_count} trận đấu vào Database!")
        
    except FileNotFoundError:
        print("❌ Lỗi: Không tìm thấy file 'worldcup_2026_upcoming_matches.csv'. Hãy đảm bảo file đang nằm cùng thư mục với script này.")
    except Exception as e:
        print(f"❌ Có lỗi xảy ra trong quá trình cập nhật: {str(e)}")
        conn.rollback()
    finally:
        # Đóng kết nối
        conn.close()

if __name__ == "__main__":
    seed_database()