"""
Shared pytest fixtures: a small synthetic CS2 match.

The fixture mirrors the exact JSON shape the Go parser emits so tests
run with no demo file and no Go toolchain. Two players per team, a few
rounds, hand-computed expected values documented inline.
"""
import pytest


@pytest.fixture
def match():
    """
    Minimal 2v2 match, 4 rounds.
    TeamA = anna(1), bob(2)   — started CT
    TeamB = cleo(3), dan(4)   — started T

    Kills (hand-traced):
      R1: anna>cleo (entry, HS), bob>dan          -> TeamA 2, TeamB 0  CT wins
      R2: dan>bob (entry), cleo>anna              -> TeamA 0, TeamB 2  T wins
      R3: anna>dan (entry), cleo>anna, bob>cleo   -> TeamA 2, TeamB 1  CT wins
      R4: cleo>anna (entry), dan>bob              -> TeamA 0, TeamB 2  T wins
    """
    return {
        "map_name": "de_test",
        "total_rounds": 4,
        "tick_rate": 64,
        "ct_score": 2, "t_score": 2,
        "team_a_score": 2, "team_b_score": 2,
        "player_summaries": [
            {"steam_id": 1, "name": "anna", "team": "TeamA", "kills": 3, "deaths": 3,
             "adr": 90.0, "kast": 0.75, "headshots": 1, "entry_kills": 2, "trade_kills": 0, "flash_assists": 1},
            {"steam_id": 2, "name": "bob", "team": "TeamA", "kills": 2, "deaths": 2,
             "adr": 70.0, "kast": 0.50, "headshots": 0, "entry_kills": 0, "trade_kills": 1, "flash_assists": 0},
            {"steam_id": 3, "name": "cleo", "team": "TeamB", "kills": 3, "deaths": 2,
             "adr": 95.0, "kast": 1.00, "headshots": 2, "entry_kills": 1, "trade_kills": 1, "flash_assists": 0},
            {"steam_id": 4, "name": "dan", "team": "TeamB", "kills": 2, "deaths": 3,
             "adr": 60.0, "kast": 0.50, "headshots": 0, "entry_kills": 1, "trade_kills": 0, "flash_assists": 0},
        ],
        "rounds": [
            {"round": 1, "start_tick": 0,    "end_tick": 1000, "winner": "CT", "ct_equip_value": 4500, "t_equip_value": 800},
            {"round": 2, "start_tick": 1000, "end_tick": 2000, "winner": "T",  "ct_equip_value": 5000, "t_equip_value": 4800},
            {"round": 3, "start_tick": 2000, "end_tick": 3000, "winner": "CT", "ct_equip_value": 5000, "t_equip_value": 5000},
            {"round": 4, "start_tick": 3000, "end_tick": 4000, "winner": "T",  "ct_equip_value": 1500, "t_equip_value": 5000},
        ],
        "kills": [
            # R1
            {"round": 1, "tick": 100, "killer_steam_id": 1, "killer_name": "anna", "killer_side": "CT", "killer_team": "TeamA",
             "victim_steam_id": 3, "victim_name": "cleo", "victim_side": "T", "victim_team": "TeamB",
             "weapon": "AK-47", "headshot": True,  "is_entry": True,  "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 300, "y": 400, "z": 0}},  # dist 500
            {"round": 1, "tick": 200, "killer_steam_id": 2, "killer_name": "bob", "killer_side": "CT", "killer_team": "TeamA",
             "victim_steam_id": 4, "victim_name": "dan", "victim_side": "T", "victim_team": "TeamB",
             "weapon": "M4A4", "headshot": False, "is_entry": False, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 0, "y": 1000, "z": 0}},  # dist 1000
            # R2
            {"round": 2, "tick": 1100, "killer_steam_id": 4, "killer_name": "dan", "killer_side": "T", "killer_team": "TeamB",
             "victim_steam_id": 2, "victim_name": "bob", "victim_side": "CT", "victim_team": "TeamA",
             "weapon": "AK-47", "headshot": False, "is_entry": True, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 100, "y": 0, "z": 0}},
            {"round": 2, "tick": 1200, "killer_steam_id": 3, "killer_name": "cleo", "killer_side": "T", "killer_team": "TeamB",
             "victim_steam_id": 1, "victim_name": "anna", "victim_side": "CT", "victim_team": "TeamA",
             "weapon": "AWP", "headshot": True, "is_entry": False, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 0, "y": 0, "z": 0}},  # dist 0 (skipped in death heatmap)
            # R3
            {"round": 3, "tick": 2100, "killer_steam_id": 1, "killer_name": "anna", "killer_side": "CT", "killer_team": "TeamA",
             "victim_steam_id": 4, "victim_name": "dan", "victim_side": "T", "victim_team": "TeamB",
             "weapon": "AK-47", "headshot": False, "is_entry": True, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 600, "y": 800, "z": 0}},  # dist 1000
            {"round": 3, "tick": 2200, "killer_steam_id": 3, "killer_name": "cleo", "killer_side": "T", "killer_team": "TeamB",
             "victim_steam_id": 1, "victim_name": "anna", "victim_side": "CT", "victim_team": "TeamA",
             "weapon": "AWP", "headshot": True, "is_entry": False, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 50, "y": 0, "z": 0}},
            {"round": 3, "tick": 2250, "killer_steam_id": 2, "killer_name": "bob", "killer_side": "CT", "killer_team": "TeamA",
             "victim_steam_id": 3, "victim_name": "cleo", "victim_side": "T", "victim_team": "TeamB",
             "weapon": "M4A4", "headshot": False, "is_entry": False, "is_trade": True,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 30, "y": 40, "z": 0}},  # dist 50
            # R4
            {"round": 4, "tick": 3100, "killer_steam_id": 3, "killer_name": "cleo", "killer_side": "T", "killer_team": "TeamB",
             "victim_steam_id": 1, "victim_name": "anna", "victim_side": "CT", "victim_team": "TeamA",
             "weapon": "AWP", "headshot": False, "is_entry": True, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 0, "y": 200, "z": 0}},
            {"round": 4, "tick": 3200, "killer_steam_id": 4, "killer_name": "dan", "killer_side": "T", "killer_team": "TeamB",
             "victim_steam_id": 2, "victim_name": "bob", "victim_side": "CT", "victim_team": "TeamA",
             "weapon": "Deagle", "headshot": False, "is_entry": False, "is_trade": False,
             "killer_pos": {"x": 0, "y": 0, "z": 0}, "victim_pos": {"x": 100, "y": 0, "z": 0}},
        ],
        "damages": [
            {"round": 1, "attacker_steam_id": 1, "weapon": "HE Grenade", "health_damage": 40, "hit_group": "Stomach"},
            {"round": 1, "attacker_steam_id": 1, "weapon": "AK-47",      "health_damage": 100, "hit_group": "Head"},
            {"round": 3, "attacker_steam_id": 3, "weapon": "Molotov",    "health_damage": 25, "hit_group": "Stomach"},
        ],
        "flashes": [
            {"round": 1, "thrower_steam_id": 1, "is_team_flash": False, "duration_seconds": 2.5},
            {"round": 1, "thrower_steam_id": 1, "is_team_flash": True,  "duration_seconds": 1.0},
            {"round": 2, "thrower_steam_id": 3, "is_team_flash": False, "duration_seconds": 3.0},
        ],
        "grenades": [
            {"round": 1, "thrower_steam_id": 1, "grenade_type": "HE Grenade"},
            {"round": 1, "thrower_steam_id": 1, "grenade_type": "Flashbang"},
            {"round": 3, "thrower_steam_id": 3, "grenade_type": "Molotov"},
        ],
        "bomb_events": [
            {"round": 2, "event_type": "planted", "player_name": "dan",  "site": "A"},
            {"round": 2, "event_type": "exploded"},
            {"round": 4, "event_type": "planted", "player_name": "cleo", "site": "B"},
            {"round": 4, "event_type": "defused", "player_name": "anna"},
        ],
        "player_rounds": {
            "1": [{"round": 1, "survived": True}, {"round": 2, "survived": False},
                  {"round": 3, "survived": False}, {"round": 4, "survived": False}],
            "2": [{"round": 1, "survived": True}, {"round": 2, "survived": False},
                  {"round": 3, "survived": True}, {"round": 4, "survived": False}],
            "3": [{"round": 1, "survived": False}, {"round": 2, "survived": True},
                  {"round": 3, "survived": False}, {"round": 4, "survived": True}],
            "4": [{"round": 1, "survived": False}, {"round": 2, "survived": True},
                  {"round": 3, "survived": False}, {"round": 4, "survived": True}],
        },
        "position_samples": [
            {"round": 1, "steam_id": 1, "is_alive": True,  "pos": {"x": 10, "y": 20, "z": 0}},
            {"round": 1, "steam_id": 1, "is_alive": True,  "pos": {"x": 15, "y": 25, "z": 0}},
            {"round": 1, "steam_id": 3, "is_alive": False, "pos": {"x": 99, "y": 99, "z": 0}},
        ],
    }


@pytest.fixture
def empty_match():
    """Empty but structurally valid match — for edge-case tests."""
    return {
        "map_name": "", "total_rounds": 0, "tick_rate": 64,
        "ct_score": 0, "t_score": 0,
        "player_summaries": [], "rounds": [], "kills": [],
        "damages": [], "flashes": [], "grenades": [],
        "bomb_events": [], "player_rounds": {}, "position_samples": [],
    }
