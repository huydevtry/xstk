from __future__ import annotations

import random
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "betting_db.db"
SEED_DOMAIN = "seed.local"
SEED_MATCH_IDS = list(range(9001, 9011))
RANDOM_SEED = 20260618

AVATAR_COLORS = [
    "#6366f1",
    "#8b5cf6",
    "#ec4899",
    "#f43f5e",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#06b6d4",
    "#3b82f6",
    "#a855f7",
    "#84cc16",
]

USER_NAMES = [
    "Bao An",
    "Minh Tri",
    "Quang Huy",
    "Khanh Linh",
    "Gia Han",
    "Thanh Nam",
    "My Duyen",
    "Hoang Son",
    "Lan Chi",
    "Duc Anh",
    "Phuong Nhi",
    "Tuan Kiet",
    "Ngoc Mai",
    "Nhat Minh",
    "Bao Chau",
    "Thien Long",
    "Kim Ngan",
    "Gia Bao",
    "Thu Ha",
    "Le Quan",
]

BET_TAUNTS = [
    "len thuyen nhe tay",
    "vao cua nay vi so lieu dep",
    "cam thay co mui tien",
    "theo linh cam 3 giay",
    "vao cua khong can hoi",
    "lan nay chac chan hon",
]

TEXT_STATUS_SNIPPETS = [
    "sang nay vao app thay keo dep nen tinh than len cao",
    "hom nay chu nha co mui rat ngon, toi xin theo nhe",
    "cua hoa nhin hien nhung biet dau lai ra qua",
    "da qua lau roi moi gap mot loat keo can doi the nay",
    "toi van giu quan diem vao it ma chat",
    "dang cho tran live no bung no mot chut",
    "neu toi sai keo nay thi toi di an bun bo",
    "nhin tong quy ma thay nhieu tam hon hon",
    "toi khong theo dam dong, toi theo so",
    "chu nha hom nay duoc long toi that su",
]

REACTION_SNIPPETS = [
    "tran nay xem xong thay dung la doi luc phai tin vao linh cam",
    "ket qua nay dung kieu vao som thi cuoi sau",
    "thua keo nhung van phuc team da chien het minh",
    "du lieu da noi dung, chi la dam dong chua theo kip",
    "qua nay ma khong dang status thi phi ca cam xuc",
    "keo nay dung la mot bua an tinh than thinh soan",
]


def dt_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def build_matches(now: datetime) -> list[dict]:
    return [
        {
            "id": 9001,
            "home_team": "Vietnam",
            "away_team": "Thailand",
            "home_icon": None,
            "away_icon": None,
            "handicap": -0.5,
            "home_score": 2,
            "away_score": 1,
            "status": "finished",
            "start_time": now - timedelta(days=8, hours=5),
        },
        {
            "id": 9002,
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "home_icon": None,
            "away_icon": None,
            "handicap": 0.0,
            "home_score": 1,
            "away_score": 1,
            "status": "finished",
            "start_time": now - timedelta(days=7, hours=2),
        },
        {
            "id": 9003,
            "home_team": "Inter Milan",
            "away_team": "Juventus",
            "home_icon": None,
            "away_icon": None,
            "handicap": 1.0,
            "home_score": 0,
            "away_score": 1,
            "status": "finished",
            "start_time": now - timedelta(days=6, hours=3),
        },
        {
            "id": 9004,
            "home_team": "PSG",
            "away_team": "Monaco",
            "home_icon": None,
            "away_icon": None,
            "handicap": 0.75,
            "home_score": 1,
            "away_score": 2,
            "status": "finished",
            "start_time": now - timedelta(days=4, hours=6),
        },
        {
            "id": 9005,
            "home_team": "Liverpool",
            "away_team": "Tottenham",
            "home_icon": None,
            "away_icon": None,
            "handicap": -1.5,
            "home_score": 3,
            "away_score": 1,
            "status": "finished",
            "start_time": now - timedelta(days=3, hours=4),
        },
        {
            "id": 9006,
            "home_team": "Atletico",
            "away_team": "Sevilla",
            "home_icon": None,
            "away_icon": None,
            "handicap": 0.0,
            "home_score": 0,
            "away_score": 2,
            "status": "finished",
            "start_time": now - timedelta(days=2, hours=1),
        },
        {
            "id": 9007,
            "home_team": "Leverkusen",
            "away_team": "Dortmund",
            "home_icon": None,
            "away_icon": None,
            "handicap": -0.25,
            "home_score": 0,
            "away_score": 0,
            "status": "upcoming",
            "start_time": now + timedelta(hours=18),
        },
        {
            "id": 9008,
            "home_team": "Real Madrid",
            "away_team": "Barcelona",
            "home_icon": None,
            "away_icon": None,
            "handicap": 0.0,
            "home_score": 0,
            "away_score": 0,
            "status": "upcoming",
            "start_time": now + timedelta(days=2, hours=3),
        },
        {
            "id": 9009,
            "home_team": "Bayern",
            "away_team": "Leipzig",
            "home_icon": None,
            "away_icon": None,
            "handicap": -1.0,
            "home_score": 1,
            "away_score": 0,
            "status": "live",
            "start_time": now - timedelta(hours=1),
        },
        {
            "id": 9010,
            "home_team": "Milan",
            "away_team": "Napoli",
            "home_icon": None,
            "away_icon": None,
            "handicap": 0.0,
            "home_score": 2,
            "away_score": 2,
            "home_penalty_score": 4,
            "away_penalty_score": 3,
            "status": "finished",
            "start_time": now - timedelta(hours=14),
        },
    ]


def match_allowed_choices(match: dict) -> list[str]:
    if float(match["handicap"]) % 1 != 0:
        return ["HOME", "AWAY"]
    return ["HOME", "DRAW", "AWAY"]


def winning_choice(match: dict) -> str:
    adjusted_home = float(match["home_score"]) + float(match["handicap"])
    adjusted_away = float(match["away_score"])
    if adjusted_home > adjusted_away:
        return "HOME"
    if adjusted_home < adjusted_away:
        return "AWAY"
    return "DRAW"


def handicap_component_lines(handicap: float) -> list[Decimal]:
    line = Decimal(str(handicap)).quantize(Decimal("0.01"))
    fraction = abs(line) % 1
    if fraction in {Decimal("0.25"), Decimal("0.75")}:
        quarter = Decimal("0.25")
        return [line - quarter, line + quarter]
    return [line]


def two_way_component_result(match: dict, handicap_line: Decimal, choice: str) -> str:
    adjusted_home = Decimal(str(match["home_score"])) + handicap_line
    adjusted_away = Decimal(str(match["away_score"]))
    if adjusted_home > adjusted_away:
        winner = "HOME"
    elif adjusted_home < adjusted_away:
        winner = "AWAY"
    else:
        winner = None
    if winner is None:
        return "REFUND"
    return "WIN" if choice == winner else "LOSE"


def settle_two_way_bets(grouped_bets: list[dict], match: dict) -> None:
    component_lines = handicap_component_lines(float(match["handicap"]))
    divisor = Decimal(len(component_lines))
    exact_returns = {id(bet): Decimal("0") for bet in grouped_bets}
    component_results = {id(bet): [] for bet in grouped_bets}

    for handicap_line in component_lines:
        stake_parts = {id(bet): Decimal(str(bet["stake"])) / divisor for bet in grouped_bets}
        total_pool = sum(stake_parts.values(), Decimal("0"))
        natural_results = {
            id(bet): two_way_component_result(match, handicap_line, str(bet["choice"]))
            for bet in grouped_bets
        }
        winner_ids = [bet_id for bet_id, result in natural_results.items() if result == "WIN"]
        if not winner_ids:
            for bet in grouped_bets:
                bet_id = id(bet)
                component_results[bet_id].append("REFUND")
                exact_returns[bet_id] += stake_parts[bet_id]
            continue

        total_winner_stake = sum((stake_parts[bet_id] for bet_id in winner_ids), Decimal("0"))
        for bet in grouped_bets:
            bet_id = id(bet)
            result = natural_results[bet_id]
            component_results[bet_id].append(result)
            if result == "WIN":
                exact_returns[bet_id] += (total_pool * stake_parts[bet_id]) / total_winner_stake
            elif result == "REFUND":
                exact_returns[bet_id] += stake_parts[bet_id]

    allocated_returns = {
        bet_id: int(value.to_integral_value(rounding=ROUND_DOWN))
        for bet_id, value in exact_returns.items()
    }
    total_allocated = sum(allocated_returns.values())
    total_stake = sum(int(bet["stake"]) for bet in grouped_bets)
    remainder = max(0, total_stake - total_allocated)
    fractional_items = sorted(
        (
            (exact_returns[id(bet)] - Decimal(allocated_returns[id(bet)]), bet["created_at"], id(bet))
            for bet in grouped_bets
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    for index in range(remainder):
        _, _, bet_id = fractional_items[index]
        allocated_returns[bet_id] += 1

    for bet in grouped_bets:
        bet_id = id(bet)
        results = set(component_results[bet_id])
        payout = allocated_returns[bet_id]
        if results == {"REFUND"} and payout == int(bet["stake"]):
            bet["points_earned"] = None
        else:
            bet["points_earned"] = payout


def insert_matches(cursor: sqlite3.Cursor, matches: list[dict], now: datetime) -> dict[int, dict]:
    match_map: dict[int, dict] = {}
    for match in matches:
        end_time = match["start_time"] + timedelta(hours=2)
        resolved_at = end_time + timedelta(minutes=15) if match["status"] == "finished" else None
        payload = {
            **match,
            "end_time": end_time,
            "resolved_at": resolved_at,
        }
        match_map[match["id"]] = payload
        cursor.execute(
            """
            INSERT INTO matches (
                id, home_team, home_icon, away_team, away_icon,
                home_score, away_score, home_penalty_score, away_penalty_score, handicap, status,
                start_time, end_time, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["home_team"],
                payload["home_icon"],
                payload["away_team"],
                payload["away_icon"],
                payload["home_score"],
                payload["away_score"],
                payload.get("home_penalty_score"),
                payload.get("away_penalty_score"),
                payload["handicap"],
                payload["status"],
                dt_text(payload["start_time"]),
                dt_text(payload["end_time"]),
                dt_text(payload["resolved_at"]) if payload["resolved_at"] else None,
            ),
        )
    return match_map


def ensure_match_penalty_columns(cursor: sqlite3.Cursor) -> None:
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(matches)").fetchall()}
    if "home_penalty_score" not in columns:
        cursor.execute("ALTER TABLE matches ADD COLUMN home_penalty_score INTEGER")
    if "away_penalty_score" not in columns:
        cursor.execute("ALTER TABLE matches ADD COLUMN away_penalty_score INTEGER")


def build_users(now: datetime) -> list[dict]:
    users = []
    for index, name in enumerate(USER_NAMES, start=1):
        users.append(
            {
                "id": uuid.uuid4().hex,
                "email": f"demo_user_{index:02d}@{SEED_DOMAIN}",
                "display_name": name,
                "avatar_url": None,
                "avatar_color": AVATAR_COLORS[(index - 1) % len(AVATAR_COLORS)],
                "created_at": datetime(now.year, now.month, max(1, now.day - (index % 9 + 1)), 8 + (index % 7), 15, 0),
                "base_points": 12000 + index * 180,
            }
        )
    return users


def build_bets(users: list[dict], match_map: dict[int, dict], rng: random.Random) -> list[dict]:
    finished_match_ids = [9001, 9002, 9003, 9004, 9005, 9006, 9010]
    open_match_ids = [9007, 9008, 9009]
    bets: list[dict] = []

    for index, user in enumerate(users):
        chosen_finished = rng.sample(finished_match_ids, 5)
        chosen_open = rng.sample(open_match_ids, 2)
        chosen_matches = chosen_finished + chosen_open
        for order, match_id in enumerate(chosen_matches):
            match = match_map[match_id]
            choices = match_allowed_choices(match)
            if match_id == 9010:
                choices = ["HOME", "AWAY"]
            choice = choices[(index + order + rng.randint(0, 2)) % len(choices)]
            stake = rng.choice([80, 100, 120, 150, 180, 220, 260, 300, 360, 420])
            created_at = match["start_time"] - timedelta(hours=rng.randint(2, 22), minutes=rng.randint(0, 55))
            bets.append(
                {
                    "user_id": user["id"],
                    "match_id": match_id,
                    "choice": choice,
                    "stake": stake,
                    "taunt_text": BET_TAUNTS[(index + order) % len(BET_TAUNTS)],
                    "points_earned": None,
                    "created_at": created_at,
                }
            )
    return bets


def settle_bets(bets: list[dict], match_map: dict[int, dict]) -> None:
    bets_by_match: dict[int, list[dict]] = defaultdict(list)
    for bet in bets:
        bets_by_match[bet["match_id"]].append(bet)

    for match_id, grouped_bets in bets_by_match.items():
        match = match_map[match_id]
        if match["status"] != "finished" or not match["resolved_at"]:
            continue

        if float(match["handicap"]) % 1 != 0:
            settle_two_way_bets(grouped_bets, match)
            continue

        winner = winning_choice(match)
        winners = [bet for bet in grouped_bets if bet["choice"] == winner]
        total_pool = sum(int(bet["stake"]) for bet in grouped_bets)
        stakes_on_winner = sum(int(bet["stake"]) for bet in winners)
        refunded = not winners or stakes_on_winner == 0

        if refunded:
            for bet in grouped_bets:
                bet["points_earned"] = None
            continue

        exact_rewards = []
        allocated_total = 0
        for bet in grouped_bets:
            if bet["choice"] != winner:
                bet["points_earned"] = 0
                continue
            exact = (total_pool * bet["stake"]) / stakes_on_winner
            reward = int(exact)
            fraction = exact - reward
            exact_rewards.append((bet, reward, fraction))
            allocated_total += reward

        remainder = total_pool - allocated_total
        exact_rewards.sort(key=lambda item: (-item[2], item[0]["created_at"], item[0]["user_id"]))
        for idx, (bet, reward, _) in enumerate(exact_rewards):
            final_reward = reward + (1 if idx < remainder else 0)
            bet["points_earned"] = final_reward


def apply_user_totals(users: list[dict], bets: list[dict], match_map: dict[int, dict]) -> None:
    totals = {user["id"]: int(user["base_points"]) for user in users}
    for bet in bets:
        totals[bet["user_id"]] -= int(bet["stake"])
        match = match_map[bet["match_id"]]
        if match["status"] == "finished" and match["resolved_at"]:
            if bet["points_earned"] is None:
                totals[bet["user_id"]] += int(bet["stake"])
            elif int(bet["points_earned"]) > 0:
                totals[bet["user_id"]] += int(bet["points_earned"])
    for user in users:
        user["total_points"] = max(0, totals[user["id"]])


def build_posts(users: list[dict], bets: list[dict], match_map: dict[int, dict], rng: random.Random) -> list[dict]:
    bets_by_user: dict[str, list[dict]] = defaultdict(list)
    for bet in bets:
        bets_by_user[bet["user_id"]].append(bet)

    posts: list[dict] = []
    for index, user in enumerate(users):
        user_posts = []
        for status_index in range(2):
            created_at = datetime.now() - timedelta(days=(index + status_index) % 6, hours=2 * status_index + index % 5)
            content = TEXT_STATUS_SNIPPETS[(index + status_index) % len(TEXT_STATUS_SNIPPETS)]
            user_posts.append(
                {
                    "user_id": user["id"],
                    "content": content,
                    "post_type": "text",
                    "match_id": None,
                    "created_at": created_at,
                }
            )

        finished_bets = [
            bet for bet in bets_by_user[user["id"]]
            if match_map[bet["match_id"]]["status"] == "finished" and match_map[bet["match_id"]]["resolved_at"]
        ]
        if index % 2 == 0 and finished_bets:
            reaction_bet = finished_bets[index % len(finished_bets)]
            reaction_time = match_map[reaction_bet["match_id"]]["resolved_at"] + timedelta(hours=2 + (index % 5))
            user_posts.append(
                {
                    "user_id": user["id"],
                    "content": REACTION_SNIPPETS[index % len(REACTION_SNIPPETS)],
                    "post_type": "match_reaction",
                    "match_id": reaction_bet["match_id"],
                    "created_at": reaction_time,
                }
            )

        user_posts.sort(key=lambda item: (item["created_at"], item["post_type"]))
        posts.extend(user_posts)
    return posts


def cleanup_seed_data(cursor: sqlite3.Cursor) -> None:
    seeded_user_ids = [
        row[0]
        for row in cursor.execute(
            "SELECT id FROM users WHERE email LIKE ?",
            (f"%@{SEED_DOMAIN}",),
        ).fetchall()
    ]
    if seeded_user_ids:
        placeholders = ",".join("?" for _ in seeded_user_ids)
        cursor.execute(f"DELETE FROM profile_status_posts WHERE user_id IN ({placeholders})", seeded_user_ids)
        cursor.execute(f"DELETE FROM bets WHERE user_id IN ({placeholders})", seeded_user_ids)
        cursor.execute(f"DELETE FROM users WHERE id IN ({placeholders})", seeded_user_ids)

    match_placeholders = ",".join("?" for _ in SEED_MATCH_IDS)
    cursor.execute(f"DELETE FROM profile_status_posts WHERE match_id IN ({match_placeholders})", SEED_MATCH_IDS)
    cursor.execute(f"DELETE FROM bets WHERE match_id IN ({match_placeholders})", SEED_MATCH_IDS)
    cursor.execute(f"DELETE FROM matches WHERE id IN ({match_placeholders})", SEED_MATCH_IDS)


def insert_users(cursor: sqlite3.Cursor, users: list[dict]) -> None:
    for user in users:
        cursor.execute(
            """
            INSERT INTO users (
                id, email, display_name,
                total_points, avatar_url, avatar_color, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user["email"],
                user["display_name"],
                user["total_points"],
                user["avatar_url"],
                user["avatar_color"],
                dt_text(user["created_at"]),
            ),
        )


def insert_bets(cursor: sqlite3.Cursor, bets: list[dict]) -> None:
    for bet in bets:
        cursor.execute(
            """
            INSERT INTO bets (
                user_id, match_id, choice, stake, taunt_text, points_earned, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bet["user_id"],
                bet["match_id"],
                bet["choice"],
                bet["stake"],
                bet["taunt_text"],
                bet["points_earned"],
                dt_text(bet["created_at"]),
            ),
        )


def insert_posts(cursor: sqlite3.Cursor, posts: list[dict]) -> None:
    for post in posts:
        cursor.execute(
            """
            INSERT INTO profile_status_posts (
                user_id, content, created_at, post_type, match_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                post["user_id"],
                post["content"],
                dt_text(post["created_at"]),
                post["post_type"],
                post["match_id"],
            ),
        )


def main() -> None:
    rng = random.Random(RANDOM_SEED)
    now = datetime.now().replace(second=0, microsecond=0)
    matches = build_matches(now)
    users = build_users(now)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        ensure_match_penalty_columns(cursor)
        cleanup_seed_data(cursor)
        match_map = insert_matches(cursor, matches, now)
        bets = build_bets(users, match_map, rng)
        settle_bets(bets, match_map)
        apply_user_totals(users, bets, match_map)
        posts = build_posts(users, bets, match_map, rng)

        insert_users(cursor, users)
        insert_bets(cursor, bets)
        insert_posts(cursor, posts)
        conn.commit()

        seeded_reactions = sum(1 for post in posts if post["post_type"] == "match_reaction")
        print("Seeded local demo data successfully.")
        print(f"- users: {len(users)}")
        print(f"- matches: {len(matches)}")
        print(f"- bets: {len(bets)}")
        print(f"- posts: {len(posts)} (match reactions: {seeded_reactions})")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
