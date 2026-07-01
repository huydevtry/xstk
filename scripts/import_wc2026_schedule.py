"""
Script nhập lịch thi đấu World Cup 2026 (từ ảnh FIFA) vào DB.
Thời gian trong ảnh là giờ Việt Nam (UTC+7), convert sang UTC naive để lưu DB.
"""
import sqlite3
from datetime import datetime, timezone, timedelta

DB_PATH = "betting_db.db"
VN_OFFSET = timedelta(hours=7)

def vn_to_utc(vn_dt_str):
    """Parse datetime string in VN timezone and convert to UTC naive datetime."""
    dt = datetime.strptime(vn_dt_str, "%Y-%m-%d %H:%M")
    vn_aware = dt.replace(tzinfo=timezone(VN_OFFSET))
    utc_dt = vn_aware.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_dt

def flag(code):
    """Return flagcdn URL for a country code."""
    return f"https://flagcdn.com/w320/{code.lower()}.webp"

# All matches from the images
# Format: (home_team, home_code, away_team, away_code, vn_datetime_str, round_label)
# Note: TBD teams use empty string for icon
MATCHES = [
    # Thursday 02 July 2026 - Round of 32
    ("Belgium",      "be",  "Senegal",              "sn",  "2026-07-02 03:00", "Vòng 1/32"),
    ("USA",          "us",  "Bosnia and Herzegovina","ba",  "2026-07-02 07:00", "Vòng 1/32"),
    # Friday 03 July 2026 - Round of 32
    ("Spain",        "es",  "Austria",              "at",  "2026-07-03 02:00", "Vòng 1/32"),
    ("Portugal",     "pt",  "Croatia",              "hr",  "2026-07-03 06:00", "Vòng 1/32"),
    ("Switzerland",  "ch",  "Algeria",              "dz",  "2026-07-03 10:00", "Vòng 1/32"),
    # Saturday 04 July 2026 - Round of 32
    ("Australia",    "au",  "Egypt",                "eg",  "2026-07-04 01:00", "Vòng 1/32"),
    ("Argentina",    "ar",  "Cabo Verde",           "cv",  "2026-07-04 05:00", "Vòng 1/32"),
    ("Colombia",     "co",  "Ghana",                "gh",  "2026-07-04 08:30", "Vòng 1/32"),
    # Sunday 05 July 2026 - Round of 16
    ("Canada",       "ca",  "Morocco",              "ma",  "2026-07-05 00:00", "Vòng 1/16"),
    ("Paraguay",     "py",  "France",               "fr",  "2026-07-05 04:00", "Vòng 1/16"),
    # Monday 06 July 2026 - Round of 16
    ("Brazil",       "br",  "Norway",               "no",  "2026-07-06 03:00", "Vòng 1/16"),
    ("Mexico",       "mx",  "TBD",                  "",    "2026-07-06 07:00", "Vòng 1/16"),
    # Tuesday 07 July 2026 - Round of 16
    ("TBD",          "",    "TBD",                  "",    "2026-07-07 02:00", "Vòng 1/16"),
    ("TBD",          "",    "TBD",                  "",    "2026-07-07 07:00", "Vòng 1/16"),
    ("TBD",          "",    "TBD",                  "",    "2026-07-07 23:00", "Vòng 1/16"),
    # Wednesday 08 July 2026 - Round of 16
    ("TBD",          "",    "TBD",                  "",    "2026-07-08 03:00", "Vòng 1/16"),
    # Friday 10 July 2026 - Quarter-final
    ("TBD",          "",    "TBD",                  "",    "2026-07-10 03:00", "Tứ kết"),
    # Saturday 11 July 2026 - Quarter-final
    ("TBD",          "",    "TBD",                  "",    "2026-07-11 02:00", "Tứ kết"),
    # Sunday 12 July 2026 - Quarter-final
    ("TBD",          "",    "TBD",                  "",    "2026-07-12 04:00", "Tứ kết"),
    ("TBD",          "",    "TBD",                  "",    "2026-07-12 08:00", "Tứ kết"),
    # Wednesday 15 July 2026 - Semi-final
    ("TBD",          "",    "TBD",                  "",    "2026-07-15 02:00", "Bán kết"),
    # Thursday 16 July 2026 - Semi-final
    ("TBD",          "",    "TBD",                  "",    "2026-07-16 02:00", "Bán kết"),
    # Sunday 19 July 2026 - Play-off for third place
    ("TBD",          "",    "TBD",                  "",    "2026-07-19 04:00", "Tranh hạng 3"),
    # Monday 20 July 2026 - Final
    ("TBD",          "",    "TBD",                  "",    "2026-07-20 02:00", "Chung kết"),
]

MATCH_DURATION = timedelta(hours=2)

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Ensure round column exists
    cur.execute("PRAGMA table_info(matches)")
    cols = {row[1] for row in cur.fetchall()}
    if "round" not in cols:
        cur.execute("ALTER TABLE matches ADD COLUMN round VARCHAR")
        print("Added 'round' column to matches table.")

    inserted = 0
    skipped = 0

    for home_team, home_code, away_team, away_code, vn_dt_str, round_label in MATCHES:
        start_utc = vn_to_utc(vn_dt_str)
        end_utc = start_utc + MATCH_DURATION

        # Check if a similar match already exists (same teams, same day)
        start_date = start_utc.strftime("%Y-%m-%d")
        cur.execute(
            "SELECT id FROM matches WHERE home_team=? AND away_team=? AND date(start_time)=?",
            (home_team, away_team, start_date)
        )
        if cur.fetchone():
            print(f"  SKIP (exists): {home_team} vs {away_team} @ {vn_dt_str} VN")
            skipped += 1
            continue

        home_icon = flag(home_code) if home_code else None
        away_icon = flag(away_code) if away_code else None

        cur.execute("""
            INSERT INTO matches (home_team, home_icon, away_team, away_icon,
                                 home_score, away_score, handicap, round,
                                 status, start_time, end_time)
            VALUES (?, ?, ?, ?, 0, 0, 0.0, ?, 'upcoming', ?, ?)
        """, (home_team, home_icon, away_team, away_icon, round_label,
              start_utc.strftime("%Y-%m-%d %H:%M:%S"),
              end_utc.strftime("%Y-%m-%d %H:%M:%S")))

        print(f"  INSERT: {home_team} vs {away_team} | {round_label} | {vn_dt_str} VN → {start_utc} UTC")
        inserted += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {inserted} inserted, {skipped} skipped.")

if __name__ == "__main__":
    main()
