from datetime import datetime
from types import SimpleNamespace
import unittest

from app.services.shared import (
    _compute_two_way_settlement,
    _derive_bet_outcome,
    _match_response,
    _serialize_bet_history_entry,
)


def build_match(
    *,
    handicap: float,
    home_score: int,
    away_score: int,
    home_penalty_score=None,
    away_penalty_score=None,
):
    return SimpleNamespace(
        id=1,
        home_team="Home",
        home_icon=None,
        away_team="Away",
        away_icon=None,
        home_score=home_score,
        away_score=away_score,
        home_penalty_score=home_penalty_score,
        away_penalty_score=away_penalty_score,
        handicap=handicap,
        status="finished",
        start_time=datetime(2026, 1, 1, 12, 0, 0),
        end_time=datetime(2026, 1, 1, 14, 0, 0),
        resolved_at=datetime(2026, 1, 1, 15, 0, 0),
    )


def build_bet(*, bet_id: int, match_id: int, choice: str, stake: int, created_minute: int):
    return SimpleNamespace(
        id=bet_id,
        match_id=match_id,
        choice=choice,
        stake=stake,
        taunt_text=None,
        points_earned=None,
        created_at=datetime(2026, 1, 1, 10, created_minute, 0),
    )


class HandicapSettlementTests(unittest.TestCase):
    def assertSettlement(
        self,
        *,
        handicap: float,
        home_score: int,
        away_score: int,
        expected_home_payout,
        expected_away_payout,
        expected_home_outcome: str,
        expected_away_outcome: str,
    ):
        match = build_match(handicap=handicap, home_score=home_score, away_score=away_score)
        home_bet = build_bet(bet_id=1, match_id=match.id, choice="HOME", stake=100, created_minute=0)
        away_bet = build_bet(bet_id=2, match_id=match.id, choice="AWAY", stake=100, created_minute=1)

        settlement = _compute_two_way_settlement(match, [home_bet, away_bet])

        self.assertEqual(settlement["payout_by_bet_id"][home_bet.id], expected_home_payout)
        self.assertEqual(settlement["payout_by_bet_id"][away_bet.id], expected_away_payout)

        home_bet.points_earned = settlement["payout_by_bet_id"][home_bet.id]
        away_bet.points_earned = settlement["payout_by_bet_id"][away_bet.id]

        self.assertEqual(_derive_bet_outcome(match, home_bet), expected_home_outcome)
        self.assertEqual(_derive_bet_outcome(match, away_bet), expected_away_outcome)

    def test_minus_quarter_draw_is_half_loss_and_half_win(self):
        self.assertSettlement(
            handicap=-0.25,
            home_score=1,
            away_score=1,
            expected_home_payout=50,
            expected_away_payout=150,
            expected_home_outcome="HALF_LOSE",
            expected_away_outcome="HALF_WIN",
        )

    def test_plus_quarter_draw_is_half_win_for_home(self):
        self.assertSettlement(
            handicap=0.25,
            home_score=1,
            away_score=1,
            expected_home_payout=150,
            expected_away_payout=50,
            expected_home_outcome="HALF_WIN",
            expected_away_outcome="HALF_LOSE",
        )

    def test_minus_three_quarters_one_goal_is_half_win(self):
        self.assertSettlement(
            handicap=-0.75,
            home_score=2,
            away_score=1,
            expected_home_payout=150,
            expected_away_payout=50,
            expected_home_outcome="HALF_WIN",
            expected_away_outcome="HALF_LOSE",
        )

    def test_minus_three_quarters_two_goals_is_full_win(self):
        self.assertSettlement(
            handicap=-0.75,
            home_score=3,
            away_score=1,
            expected_home_payout=200,
            expected_away_payout=0,
            expected_home_outcome="WIN",
            expected_away_outcome="LOSE",
        )

    def test_plus_three_quarters_one_goal_loss_is_half_loss(self):
        self.assertSettlement(
            handicap=0.75,
            home_score=0,
            away_score=1,
            expected_home_payout=50,
            expected_away_payout=150,
            expected_home_outcome="HALF_LOSE",
            expected_away_outcome="HALF_WIN",
        )

    def test_half_ball_regression_still_full_win_or_lose(self):
        self.assertSettlement(
            handicap=-0.5,
            home_score=1,
            away_score=0,
            expected_home_payout=200,
            expected_away_payout=0,
            expected_home_outcome="WIN",
            expected_away_outcome="LOSE",
        )

    def test_bet_history_serializer_exposes_partial_outcome_and_reward(self):
        match = build_match(handicap=-0.25, home_score=1, away_score=1)
        bet = build_bet(bet_id=1, match_id=match.id, choice="HOME", stake=100, created_minute=0)
        bet.points_earned = 50

        payload = _serialize_bet_history_entry(
            bet=bet,
            match=match,
            can_share_reaction=False,
            has_shared_reaction=False,
        )

        self.assertEqual(payload["outcome"], "HALF_LOSE")
        self.assertEqual(payload["outcome_label"], "Thua nửa")
        self.assertEqual(payload["reward_label"], "Nhận 50d")

    def test_match_serializer_exposes_penalty_score_and_advancing_team(self):
        match = build_match(
            handicap=0,
            home_score=1,
            away_score=1,
            home_penalty_score=4,
            away_penalty_score=3,
        )

        payload = _match_response(match)

        self.assertEqual(payload["penalty_score"], "4-3")
        self.assertEqual(payload["display_score"], "1-1 (pen 4-3)")
        self.assertEqual(payload["advancing_team"]["side"], "HOME")
        self.assertEqual(payload["advancing_team"]["decided_by"], "penalties")


if __name__ == "__main__":
    unittest.main()
