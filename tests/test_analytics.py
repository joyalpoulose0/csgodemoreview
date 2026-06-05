"""
Tests for the pure analytics functions in parse_demo.py.
These are deterministic, file-free tests: they feed a hand-traced synthetic
match (see conftest.py) and assert exact expected values. No .dem file or Go
toolchain is needed.
"""
import math
import pytest

import Bridge as bridge


def test_get_player_summary_by_id(match):
    ps = bridge.get_player_summary(match, steam_id=1)
    assert ps is not None
    assert ps["name"] == "anna"

def test_get_player_summary_by_name_case_insensitive(match):
    ps = bridge.get_player_summary(match, name="ANNA")
    assert ps["steam_id"] == 1

def test_get_player_summary_missing(match):
    assert bridge.get_player_summary(match, steam_id=999) is None

def test_get_player_kills_count(match):
    # anna killed cleo (R1), dan (R3) = 2 kills
    assert len(bridge.get_player_kills(match, 1)) == 2

def test_get_player_deaths_count(match):
    # anna died R2, R3, R4 = 3 deaths
    assert len(bridge.get_player_deaths(match, 1)) == 3


# Momentum Check

def test_momentum_round1_teama_dominates(match):
    m = bridge.get_round_momentum(match)
    assert m[1] == {"team_a_kills": 2, "team_b_kills": 0, "diff": 2}

def test_momentum_round2_teamb_dominates(match):
    m = bridge.get_round_momentum(match)
    assert m[2] == {"team_a_kills": 0, "team_b_kills": 2, "diff": -2}

def test_momentum_round3_split(match):
    m = bridge.get_round_momentum(match)
    assert m[3] == {"team_a_kills": 2, "team_b_kills": 1, "diff": 1}

def test_momentum_covers_all_rounds(match):
    m = bridge.get_round_momentum(match)
    assert set(m.keys()) == {1, 2, 3, 4}


# Opening duel test

def test_opening_duels_total(match):
    # entry kills are in R1,R2,R3,R4 = 4 total
    od = bridge.get_opening_duel_stats(match)
    assert od["total_opening_duels"] == 4

def test_opening_duels_team_split(match):
    # R1 anna(A), R2 dan(B), R3 anna(A), R4 cleo(B) -> A:2, B:2
    od = bridge.get_opening_duel_stats(match)
    assert od["team_a_wins"] == 2
    assert od["team_b_wins"] == 2
    assert od["team_a_win_rate"] == 0.5
    assert od["team_b_win_rate"] == 0.5


# Economy test

def test_economy_buy_types(match):
    econ = bridge.get_economy_efficiency(match)
    by_round = {e["round"]: e for e in econ}
    # R1: CT 4500 = full, T 800 = eco
    assert by_round[1]["ct_buy_type"] == "full"
    assert by_round[1]["t_buy_type"] == "eco"
    # R4: CT 1500 = eco, T 5000 = full
    assert by_round[4]["ct_buy_type"] == "eco"
    assert by_round[4]["t_buy_type"] == "full"

def test_economy_upset_detection(match):
    # R4: T full beats... no. CT eco, T full, winner T -> not an upset (full won)
    # R1: CT full, T eco, winner CT -> not an upset
    econ = bridge.get_economy_efficiency(match)
    by_round = {e["round"]: e for e in econ}
    assert by_round[1]["upset"] is False
    assert by_round[4]["upset"] is False


# Weapon Breakdown

def test_weapon_breakdown_match_wide(match):
    wb = bridge.get_weapon_breakdown(match)
    # AK-47 used in: R1 anna, R2 dan, R3 anna = 3 kills
    assert wb["AK-47"]["kills"] == 3
    # AWP used by cleo R2, R3, R4 = 3 kills
    assert wb["AWP"]["kills"] == 3

def test_weapon_breakdown_headshot_rate(match):
    wb = bridge.get_weapon_breakdown(match)
    # AK-47: anna R1 HS=True, dan R2 HS=False, anna R3 HS=False -> 1/3
    assert wb["AK-47"]["hs_rate"] == round(1/3, 3)

def test_weapon_breakdown_filtered_by_player(match):
    wb = bridge.get_weapon_breakdown(match, steam_id=1)
    # anna only used AK-47 (R1, R3) = 2
    assert wb["AK-47"]["kills"] == 2
    assert "AWP" not in wb


# Kill distance
def test_kill_distance_anna(match):
    kd = bridge.get_kill_distance_analysis(match)
    anna = kd["1"]
    # anna's kills: cleo dist 500 (R1), dan dist 1000 (R3) -> avg 750
    assert anna["kills"] == 2
    assert anna["avg_dist"] == 750.0
    assert anna["max_dist"] == 1000.0

def test_kill_distance_filtered(match):
    kd = bridge.get_kill_distance_analysis(match, steam_id=2)
    # bob's kills: dan dist 1000 (R1), cleo dist 50 (R3)
    assert kd["2"]["kills"] == 2
    assert kd["2"]["max_dist"] == 1000.0


# Bomb Stats

def test_bomb_stats_counts(match):
    bs = bridge.get_bomb_stats(match)
    assert bs["total_plants"] == 2
    assert bs["total_defuses"] == 1
    assert bs["total_explosions"] == 1

def test_bomb_defuse_rate(match):
    bs = bridge.get_bomb_stats(match)
    # 1 defuse / 2 plants = 0.5
    assert bs["defuse_rate"] == 0.5


# Heatmap

def test_heatmap_alive_only(match):
    pts = bridge.get_heatmap_points(match, alive_only=True)
    # 2 alive samples for anna, 1 dead sample for cleo (skipped)
    assert len(pts) == 2
    assert (10, 20) in pts

def test_heatmap_include_dead(match):
    pts = bridge.get_heatmap_points(match, alive_only=False)
    assert len(pts) == 3

def test_heatmap_filtered_by_player(match):
    pts = bridge.get_heatmap_points(match, steam_id=1)
    assert len(pts) == 2


# Edge cases

def test_empty_momentum(empty_match):
    assert bridge.get_round_momentum(empty_match) == {}

def test_empty_opening_duels(empty_match):
    od = bridge.get_opening_duel_stats(empty_match)
    assert od["total_opening_duels"] == 0
    assert od["team_a_win_rate"] == 0   # no ZeroDivisionError

def test_empty_economy(empty_match):
    assert bridge.get_economy_efficiency(empty_match) == []

def test_empty_bomb_stats(empty_match):
    bs = bridge.get_bomb_stats(empty_match)
    assert bs["total_plants"] == 0
    assert bs["defuse_rate"] == 0       # no ZeroDivisionError

def test_empty_weapon_breakdown(empty_match):
    assert bridge.get_weapon_breakdown(empty_match) == {}

def test_empty_heatmap(empty_match):
    assert bridge.get_heatmap_points(empty_match) == []
