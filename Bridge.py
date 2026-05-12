"""
Python bridge to the Go parser.
Flow:
  upload a .dem file, it is parsed by Go parser which outputs a JSON file that is used by this Python bridge for further data analysis
  (.dem file → Go parser → JSON file → Python dict)
"""

from __future__ import annotations

import json
import math
import platform
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
_GO_SRC = _HERE / "parser_file"
_BINARY_NAME = "cs2parser.exe" if platform.system() == "Windows" else "cs2parser"
_BINARY = _GO_SRC / _BINARY_NAME

# Set to True to always use `go run` (skips compiled binary entirely)
FORCE_GO_RUN = False

_BLOCK_SIGNALS = [
    "Application Control policy",
    "blocked this file",
    "NativeCommandFailed",
    "ApplicationFailedException",
]


# Check for Go 

def _go_available() -> bool:
    try:
        subprocess.run(["go", "version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

# Check for builds
def ensure_compiled(force: bool = False):
    if FORCE_GO_RUN:
        return None
    if not force and _BINARY.exists():
        src_mtime = (_GO_SRC / "main.go").stat().st_mtime
        bin_mtime = _BINARY.stat().st_mtime
        if bin_mtime >= src_mtime:
            return _BINARY
    if not _go_available():
        return None
    print("[parser] compiling Go parser...")
    result = subprocess.run(
        ["go", "build", "-o", str(_BINARY), "."],
        cwd=str(_GO_SRC),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[parser] compilation failed, will use 'go run':\n{result.stderr[:500]}")
        return None
    print(f"[parser] compiled -> {_BINARY}")
    return _BINARY


def _is_blocked(result: subprocess.CompletedProcess) -> bool:
    combined = (result.stdout or "") + (result.stderr or "")
    return result.returncode != 0 and any(s in combined for s in _BLOCK_SIGNALS)


def _run_binary(binary, demo_path, out_path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), str(demo_path), str(out_path)],
        capture_output=True, text=True,
    )


def _run_go_run(demo_path, out_path) -> subprocess.CompletedProcess:
    if not _go_available():
        raise RuntimeError(
            "Go is not on PATH. Install from https://go.dev/dl/\n"
            "Or copy the binary to a path allowed by your Application Control policy."
        )
    print("[parser] using 'go run' (binary blocked or unavailable)...")
    return subprocess.run(
        ["go", "run", ".", str(demo_path), str(out_path)],
        cwd=str(_GO_SRC),
        capture_output=True, text=True,
    )


def _check_result(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"Parser exited {result.returncode}:\n"
            f"stdout: {(result.stdout or '')[:2000]}\n"
            f"stderr: {(result.stderr or '')[:2000]}"
        )


# parse demo or use cached file

def parse_demo(demo_path, output_path=None) -> dict:
    """Parse a CS2 .dem file and return a structured dict."""
    demo_path = Path(demo_path).resolve()
    if not demo_path.exists():
        raise FileNotFoundError(f"Demo not found: {demo_path}")

    use_tmp = output_path is None
    if use_tmp:
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        out_path = Path(tmp.name)
    else:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and out_path.stat().st_mtime >= demo_path.stat().st_mtime:
            print(f"[parser] using cached parse -> {out_path}")
            return json.loads(out_path.read_text(encoding="utf-8"))

    try:
        binary = ensure_compiled()
        if binary is not None:
            result = _run_binary(binary, demo_path, out_path)
            if _is_blocked(result):
                print("[parser] binary blocked -- falling back to 'go run'")
                result = _run_go_run(demo_path, out_path)
        else:
            result = _run_go_run(demo_path, out_path)
        _check_result(result)
        return json.loads(out_path.read_text(encoding="utf-8"))
    finally:
        if use_tmp:
            out_path.unlink(missing_ok=True)


# Basic stats like kills, deaths and summary

def get_player_summary(data, steam_id=None, name=None):
    """Look up a player's aggregate summary by steam ID or name."""
    for ps in data.get("player_summaries", []):
        if steam_id is not None and str(ps["steam_id"]) == str(steam_id):
            return ps
        if name is not None and ps["name"].lower() == name.lower():
            return ps
    return None


def get_player_kills(data, steam_id):
    """All kill events where this player was the killer."""
    sid = str(steam_id)
    return [k for k in data.get("kills", []) if str(k["killer_steam_id"]) == sid]


def get_player_deaths(data, steam_id):
    """All kill events where this player was the victim."""
    sid = str(steam_id)
    return [k for k in data.get("kills", []) if str(k["victim_steam_id"]) == sid]


def get_player_positions(data, steam_id):
    """Position samples for a specific player."""
    sid = str(steam_id)
    return [p for p in data.get("position_samples", []) if str(p["steam_id"]) == sid]


def get_round_events(data, round_num):
    """All events (kills, damage, flashes, grenades, bomb) for a given round."""
    return {
        "round": next((r for r in data.get("rounds", []) if r["round"] == round_num), None),
        "kills":      [k for k in data.get("kills", [])       if k["round"] == round_num],
        "damages":    [d for d in data.get("damages", [])     if d["round"] == round_num],
        "flashes":    [f for f in data.get("flashes", [])     if f["round"] == round_num],
        "grenades":   [g for g in data.get("grenades", [])    if g["round"] == round_num],
        "bomb_events":[b for b in data.get("bomb_events", []) if b["round"] == round_num],
    }


def _round_index(data):
    """
    Converts rounds list → dict indexed by round number.
    Prevents repeated bugs like .get() on list.
    """
    return {r["round"]: r for r in data.get("rounds", [])}


# per roound analysis

def get_round_momentum(data):
    """
    Per-round kill advantage (CT kills minus T kills).
    Positive = CT dominated, negative = T dominated.
    """
    rounds = data.get("rounds", [])
    kills  = data.get("kills", [])

    kills_by_round = defaultdict(lambda: {"ct": 0, "t": 0})
    for k in kills:
        side = k.get("killer_side", "")
        if side == "CT":
            kills_by_round[k["round"]]["ct"] += 1
        elif side == "T":
            kills_by_round[k["round"]]["t"] += 1

    momentum = {}
    for r in rounds:
        rnum = r["round"]
        ct = kills_by_round[rnum]["ct"]
        t  = kills_by_round[rnum]["t"]
        momentum[rnum] = {"ct_kills": ct, "t_kills": t, "diff": ct - t}

    return momentum


def get_round_win_streak(data):
    """
    Returns the longest win streak for CT and T sides,
    and which rounds each streak covers.
    """
    rounds = data.get("rounds", [])
    ct_streak = t_streak = 0
    ct_best = t_best = 0
    ct_start = t_start = 1

    for r in rounds:
        if r["winner"] == "CT":
            ct_streak += 1
            t_streak = 0
            if ct_streak > ct_best:
                ct_best = ct_streak
        else:
            t_streak += 1
            ct_streak = 0
            if t_streak > t_best:
                t_best = t_streak

    return {"ct_longest_streak": ct_best, "t_longest_streak": t_best}


def get_opening_duel_stats(data):
    """
    For each round, identify the opening duel (first kill).
    Returns win rate for CT and T side in opening duels.
    """
    kills = data.get("kills", [])
    entry_kills = [k for k in kills if k.get("is_entry")]

    ct_wins = sum(1 for k in entry_kills if k["killer_side"] == "CT")
    t_wins  = sum(1 for k in entry_kills if k["killer_side"] == "T")
    total   = ct_wins + t_wins

    return {
        "total_opening_duels": total,
        "ct_wins": ct_wins,
        "t_wins":  t_wins,
        "ct_win_rate": round(ct_wins / total, 3) if total else 0,
        "t_win_rate":  round(t_wins  / total, 3) if total else 0,
        "by_round": [
            {
                "round":       k["round"],
                "winner_name": k["killer_name"],
                "winner_side": k["killer_side"],
                "victim_name": k["victim_name"],
                "weapon":      k["weapon"],
            }
            for k in entry_kills
        ],
    }


def detect_clutches(data):
    """
    Detect 1vX clutch situations: a player who is the last alive on their team
    and gets 2+ kills in that round. Returns per-round clutch info.

    Uses kill-event ordering: once only one killer_steam_id appears in kills
    after a point, and they chain multiple kills, that's a clutch.
    """
    kills  = data.get("kills", [])
    rounds = data.get("rounds", [])
    clutches = []

    kills_by_round = defaultdict(list)
    for k in kills:
        kills_by_round[k["round"]].append(k)

    for r in rounds:
        rnum   = r["round"]
        rk     = kills_by_round[rnum]
        winner = r.get("winner", "")

        # track alive counts per side from round start (assume 5v5)
        ct_alive = 5
        t_alive  = 5
        # scan kills in tick order
        rk_sorted = sorted(rk, key=lambda x: x["tick"])

        for i, k in enumerate(rk_sorted):
            if k["killer_side"] == "CT":
                t_alive -= 1
            else:
                ct_alive -= 1

            # check if the victim's side now has exactly 1 alive
            # and the next kills are all by the same player
            if k["killer_side"] == "CT" and t_alive == 0:
                break
            if k["killer_side"] == "T" and ct_alive == 0:
                break

            # victim_side just lost someone — check if victim_side is now at 1
            victim_side_alive = ct_alive if k["victim_side"] == "CT" else t_alive
            if victim_side_alive == 1:
                # find the surviving player on victim_side
                remaining_kills = rk_sorted[i+1:]
                clutch_kills = [
                    ck for ck in remaining_kills
                    if ck["killer_side"] == k["victim_side"]
                ]
                if len(clutch_kills) >= 1:
                    clutch_player = clutch_kills[0]["killer_name"]
                    clutch_sid    = clutch_kills[0]["killer_steam_id"]
                    opponents     = (t_alive if k["victim_side"] == "CT" else ct_alive)
                    clutches.append({
                        "round":        rnum,
                        "player":       clutch_player,
                        "steam_id":     clutch_sid,
                        "side":         k["victim_side"],
                        "vs":           opponents + 1,   # 1vX
                        "kills_in_clutch": len(clutch_kills),
                        "won":          r["winner"] == k["victim_side"],
                    })
                break

    return clutches


def detect_comeback_rounds(data):
    """
    Rounds where the losing side (by kill count) still won the round.
    Indicates strong utility, clutch, or economy play.
    """
    momentum  = get_round_momentum(data)
    rounds    = data.get("rounds", [])
    comebacks = []

    for r in rounds:
        rnum   = r["round"]
        winner = r.get("winner", "")
        m      = momentum.get(rnum, {})
        ct     = m.get("ct_kills", 0)
        t      = m.get("t_kills", 0)

        # losing side by kills
        if ct > t and winner == "T":
            comebacks.append({"round": rnum, "winner": "T", "ct_kills": ct, "t_kills": t, "kill_deficit": ct - t})
        elif t > ct and winner == "CT":
            comebacks.append({"round": rnum, "winner": "CT", "ct_kills": ct, "t_kills": t, "kill_deficit": t - ct})

    return comebacks


def get_economy_efficiency(data):
    """
    For each round: equipment value spent vs round outcome.
    Identifies eco wins, force-buy wins, full-buy losses.
    """
    rounds = data.get("rounds", [])
    result = []

    for r in rounds:
        ct_val  = r.get("ct_equip_value", 0)
        t_val   = r.get("t_equip_value", 0)
        winner  = r.get("winner", "")

        ct_type = _equip_type(ct_val)
        t_type  = _equip_type(t_val)

        upset = (
            (ct_type in ("eco", "force") and t_type == "full" and winner == "CT") or
            (t_type  in ("eco", "force") and ct_type == "full" and winner == "T")
        )

        result.append({
            "round":         r["round"],
            "ct_equip":      ct_val,
            "t_equip":       t_val,
            "ct_buy_type":   ct_type,
            "t_buy_type":    t_type,
            "winner":        winner,
            "upset":         upset,
        })

    return result


def _equip_type(val: int) -> str:
    if val < 2000:   return "eco"
    if val < 4500:   return "force"
    return "full"


# Per player analysis ( a simple HLTV style rating)

def get_player_impact_score(data):
    players = data.get("player_summaries", [])
    kills   = data.get("kills", [])

    kills_by_player = defaultdict(list)
    for k in kills:
        kills_by_player[str(k["killer_steam_id"])].append(k)

    impact = {}
    for p in players:
        sid = str(p["steam_id"])
        pk  = kills_by_player[sid]

        # multi-kill round bonus
        mk_by_round = defaultdict(int)
        for k in pk:
            mk_by_round[k["round"]] += 1
        mk_bonus = sum(
            0.5 if v == 3 else 1.0 if v == 4 else 1.5
            for v in mk_by_round.values() if v >= 3
        )

        score = (
            len(pk)                          * 1.0  +
            p.get("entry_kills", 0)          * 1.5  +
            p.get("trade_kills", 0)          * 1.2  +
            p.get("flash_assists", 0)        * 0.5  +
            p.get("adr", 0)                  * 0.01 +
            mk_bonus
        )

        impact[sid] = {
            "name":  p["name"],
            "score": round(score, 2),
            "kd":    round(p["kills"] / max(p["deaths"], 1), 2),
            "adr":   round(p.get("adr", 0), 1),
            "kast":  round(p.get("kast", 0), 3),
        }

    # rank by score
    return dict(sorted(impact.items(), key=lambda x: x[1]["score"], reverse=True))


def get_weapon_breakdown(data, steam_id=None):
    """
    Kill count and headshot rate per weapon.
    Pass steam_id to filter to one player, or None for the whole match.
    """
    kills = data.get("kills", [])
    if steam_id:
        kills = [k for k in kills if str(k["killer_steam_id"]) == str(steam_id)]

    weapons: dict[str, dict] = defaultdict(lambda: {"kills": 0, "headshots": 0})
    for k in kills:
        w = k.get("weapon", "unknown")
        weapons[w]["kills"]     += 1
        weapons[w]["headshots"] += int(k.get("headshot", False))

    return {
        w: {
            "kills":     v["kills"],
            "headshots": v["headshots"],
            "hs_rate":   round(v["headshots"] / v["kills"], 3) if v["kills"] else 0,
        }
        for w, v in sorted(weapons.items(), key=lambda x: x[1]["kills"], reverse=True)
    }


def get_damage_breakdown(data, steam_id=None):
    """
    Damage dealt per hit group (head, chest, etc.) and per weapon.
    """
    damages = data.get("damages", [])
    if steam_id:
        damages = [d for d in damages if str(d["attacker_steam_id"]) == str(steam_id)]

    hitgroups: dict[str, int] = defaultdict(int)
    by_weapon:  dict[str, int] = defaultdict(int)
    total = 0

    for d in damages:
        hg  = d.get("hit_group", "unknown")
        dmg = d.get("health_damage", 0)
        hitgroups[hg]          += dmg
        by_weapon[d.get("weapon", "unknown")] += dmg
        total += dmg

    return {
        "total_damage": total,
        "by_hitgroup":  dict(sorted(hitgroups.items(), key=lambda x: x[1], reverse=True)),
        "by_weapon":    dict(sorted(by_weapon.items(),  key=lambda x: x[1], reverse=True)),
    }


def get_utility_efficiency(data):
    """
    Per-player grenade efficiency: damage dealt per grenade thrown.
    Also tracks flash efficiency (enemies blinded / flashes thrown).
    """
    grenades = data.get("grenades", [])
    damages  = data.get("damages", [])
    flashes  = data.get("flashes", [])
    summaries = {str(p["steam_id"]): p for p in data.get("player_summaries", [])}

    # only count HE / molotov / incendiary damage for utility efficiency
    util_weapons = {"HE Grenade", "Molotov", "Incendiary Grenade", "Inferno"}
    dmg_by_player: dict[str, int] = defaultdict(int)
    for d in damages:
        if d.get("weapon", "") in util_weapons:
            dmg_by_player[str(d["attacker_steam_id"])] += d.get("health_damage", 0)

    gren_by_player: dict[str, int] = defaultdict(int)
    for g in grenades:
        gren_by_player[str(g["thrower_steam_id"])] += 1

    enemy_flashes: dict[str, int] = defaultdict(int)
    team_flashes:  dict[str, int] = defaultdict(int)
    for f in flashes:
        sid = str(f["thrower_steam_id"])
        if f.get("is_team_flash"):
            team_flashes[sid]  += 1
        else:
            enemy_flashes[sid] += 1

    result = {}
    all_sids = set(dmg_by_player) | set(gren_by_player) | set(enemy_flashes)
    for sid in all_sids:
        name   = summaries.get(sid, {}).get("name", sid)
        ngren  = gren_by_player.get(sid, 0)
        ndmg   = dmg_by_player.get(sid, 0)
        nef    = enemy_flashes.get(sid, 0)
        ntf    = team_flashes.get(sid, 0)
        result[sid] = {
            "name":                  name,
            "grenades_thrown":       ngren,
            "utility_damage":        ndmg,
            "damage_per_grenade":    round(ndmg / ngren, 2) if ngren else 0,
            "enemies_flashed":       nef,
            "team_flashes":          ntf,
            "flash_efficiency":      round(nef / (nef + ntf), 3) if (nef + ntf) else 0,
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["utility_damage"], reverse=True))


def get_survival_analysis(data):
    player_rounds = data.get("player_rounds", {})
    kills         = data.get("kills", [])
    rounds        = _round_index(data)   # FIX: always dict now
    tick_rate     = max(data.get("tick_rate", 64), 1)
    summaries     = {str(p["steam_id"]): p for p in data.get("player_summaries", [])}

    deaths_by_player = defaultdict(list)
    for k in kills:
        deaths_by_player[str(k["victim_steam_id"])].append(k)

    result = {}

    for sid, rds in player_rounds.items():
        name     = summaries.get(sid, {}).get("name", sid)
        survived = sum(1 for r in rds if r.get("survived"))
        total    = len(rds)
        deaths   = deaths_by_player.get(sid, [])

        death_times = []
        for d in deaths:
            r = rounds.get(d["round"])   # now SAFE (dict lookup)
            if r:
                elapsed_ticks = d["tick"] - r["start_tick"]
                death_times.append(elapsed_ticks / tick_rate)

        traded = sum(1 for d in deaths if d.get("is_trade"))

        result[sid] = {
            "name": name,
            "rounds_played": total,
            "survived": survived,
            "survival_rate": round(survived / total, 3) if total else 0,
            "deaths": len(deaths),
            "traded_deaths": traded,
            "trade_rate": round(traded / len(deaths), 3) if deaths else 0,
            "avg_death_time_s": round(sum(death_times) / len(death_times), 1) if death_times else None,
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["survival_rate"], reverse=True))


def get_kill_distance_analysis(data, steam_id=None):
    """
    Average and median kill distance per player (or match-wide).
    Distance is in CS2 world units (1 unit ≈ 0.75 inches).
    """
    kills = data.get("kills", [])
    if steam_id:
        kills = [k for k in kills if str(k["killer_steam_id"]) == str(steam_id)]

    by_player: dict[str, list] = defaultdict(list)
    for k in kills:
        kp = k.get("killer_pos", {})
        vp = k.get("victim_pos", {})
        if kp and vp:
            dx = kp.get("x", 0) - vp.get("x", 0)
            dy = kp.get("y", 0) - vp.get("y", 0)
            dist = math.sqrt(dx*dx + dy*dy)
            by_player[str(k["killer_steam_id"])].append((dist, k["weapon"], k["headshot"]))

    summaries = {str(p["steam_id"]): p["name"] for p in data.get("player_summaries", [])}
    result = {}
    for sid, entries in by_player.items():
        dists = [e[0] for e in entries]
        dists.sort()
        n = len(dists)
        result[sid] = {
            "name":     summaries.get(sid, sid),
            "kills":    n,
            "avg_dist": round(sum(dists) / n, 1) if n else 0,
            "med_dist": round(dists[n // 2], 1) if n else 0,
            "max_dist": round(max(dists), 1) if n else 0,
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["avg_dist"], reverse=True))


def get_flash_analysis(data):
    """
    Per-thrower flash stats: enemies blinded, average duration, team flash count.
    Also returns the most effective flashes (longest duration on enemies).
    """
    flashes   = data.get("flashes", [])
    summaries = {str(p["steam_id"]): p["name"] for p in data.get("player_summaries", [])}

    by_thrower: dict[str, dict] = defaultdict(lambda: {
        "enemy_flashes": 0, "team_flashes": 0,
        "total_enemy_duration": 0.0, "top_flash": 0.0,
    })

    for f in flashes:
        sid = str(f["thrower_steam_id"])
        dur = f.get("duration_seconds", 0)
        if f.get("is_team_flash"):
            by_thrower[sid]["team_flashes"] += 1
        else:
            by_thrower[sid]["enemy_flashes"]         += 1
            by_thrower[sid]["total_enemy_duration"]  += dur
            by_thrower[sid]["top_flash"]             = max(by_thrower[sid]["top_flash"], dur)

    result = {}
    for sid, v in by_thrower.items():
        nef = v["enemy_flashes"]
        result[sid] = {
            "name":              summaries.get(sid, sid),
            "enemy_flashes":     nef,
            "team_flashes":      v["team_flashes"],
            "avg_duration_s":    round(v["total_enemy_duration"] / nef, 2) if nef else 0,
            "best_flash_s":      round(v["top_flash"], 2),
            "flash_efficiency":  round(nef / max(nef + v["team_flashes"], 1), 3),
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["enemy_flashes"], reverse=True))


def get_bomb_stats(data):
    """
    Bomb plant / defuse / explode summary per player and per site.
    """
    bomb_events = data.get("bomb_events", [])
    summaries   = {str(p["steam_id"]): p["name"] for p in data.get("player_summaries", [])}

    plants   = [b for b in bomb_events if b["event_type"] == "planted"]
    defuses  = [b for b in bomb_events if b["event_type"] == "defused"]
    explodes = [b for b in bomb_events if b["event_type"] == "exploded"]

    plants_by_player:  dict[str, int] = defaultdict(int)
    defuses_by_player: dict[str, int] = defaultdict(int)
    plants_by_site:    dict[str, int] = defaultdict(int)

    for b in plants:
        plants_by_player[b.get("player_name", "?")] += 1
        plants_by_site[b.get("site", "?")] += 1
    for b in defuses:
        defuses_by_player[b.get("player_name", "?")] += 1

    return {
        "total_plants":         len(plants),
        "total_defuses":        len(defuses),
        "total_explosions":     len(explodes),
        "defuse_rate":          round(len(defuses) / len(plants), 3) if plants else 0,
        "plants_by_site":       dict(plants_by_site),
        "top_planters":         dict(sorted(plants_by_player.items(),  key=lambda x: x[1], reverse=True)),
        "top_defusers":         dict(sorted(defuses_by_player.items(), key=lambda x: x[1], reverse=True)),
    }


def get_heatmap_points(data, steam_id=None, alive_only=True):
    """
    Returns (x, y) position tuples for heatmap plotting.
    Positions are sampled from the Go parser every 32 ticks.
    """
    positions = data.get("position_samples", [])
    if steam_id:
        positions = [p for p in positions if str(p["steam_id"]) == str(steam_id)]
    if alive_only:
        positions = [p for p in positions if p.get("is_alive")]
    return [(p["pos"]["x"], p["pos"]["y"]) for p in positions if "pos" in p]


def get_death_heatmap_points(data, steam_id=None):
    """
    Returns (x, y) positions where kills happened (victim position).
    Useful for generating death heatmaps.
    """
    kills = data.get("kills", [])
    if steam_id:
        kills = [k for k in kills if str(k["victim_steam_id"]) == str(steam_id)]
    return [
        (k["victim_pos"]["x"], k["victim_pos"]["y"])
        for k in kills if k.get("victim_pos")
    ]


# Generate analytics

def generate_full_analytics(data):
    return {
        # match level
        "momentum":         get_round_momentum(data),
        "win_streaks":      get_round_win_streak(data),
        "opening_duels":    get_opening_duel_stats(data),
        "economy":          get_economy_efficiency(data),
        "comebacks":        detect_comeback_rounds(data),
        "bomb_stats":       get_bomb_stats(data),

        # player level
        "clutches":         detect_clutches(data),
        "impact":           get_player_impact_score(data),
        "utility":          get_utility_efficiency(data),
        "survival":         get_survival_analysis(data),
        "kill_distance":    get_kill_distance_analysis(data),
        "flash_analysis":   get_flash_analysis(data),
        "weapon_breakdown": get_weapon_breakdown(data),
        "damage_breakdown": get_damage_breakdown(data),
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python parse_demo.py <demo.dem> [output.json]")
        sys.exit(1)

    demo = sys.argv[1]
    out  = sys.argv[2] if len(sys.argv) >= 3 else None
    data = parse_demo(demo, out)

    print(f"\n=== {data['map_name']} | {data['total_rounds']} rounds | "
          f"CT {data['ct_score']} - {data['t_score']} T ===\n")

    print("── Player Summaries ──────────────────────────────")
    for ps in data["player_summaries"]:
        kd = ps["kills"] / max(ps["deaths"], 1)
        print(f"  {ps['name']:20s}  K/D={kd:.2f}  ADR={ps['adr']:.1f}  "
              f"KAST={ps['kast']:.0%}  HS={ps['headshots']}  "
              f"Entry={ps['entry_kills']}  Trade={ps['trade_kills']}")

    analytics = generate_full_analytics(data)

    print("\n── Opening Duel Win Rates ────────────────────────")
    od = analytics["opening_duels"]
    print(f"  CT: {od['ct_win_rate']:.0%}  T: {od['t_win_rate']:.0%}  ({od['total_opening_duels']} duels)")

    print("\n── Clutches ──────────────────────────────────────")
    for c in analytics["clutches"]:
        won = "WON" if c["won"] else "LOST"
        print(f"  R{c['round']:>2}  {c['player']:20s}  1v{c['vs']}  {c['kills_in_clutch']}K  {won}")

    print("\n── Bomb Stats ────────────────────────────────────")
    bs = analytics["bomb_stats"]
    print(f"  Plants: {bs['total_plants']}  Defuses: {bs['total_defuses']}  "
          f"Explosions: {bs['total_explosions']}  Defuse rate: {bs['defuse_rate']:.0%}")
    print(f"  By site: {bs['plants_by_site']}")

    print("\n── Impact Scores ─────────────────────────────────")
    for sid, imp in analytics["impact"].items():
        print(f"  {imp['name']:20s}  score={imp['score']:.2f}  "
              f"K/D={imp['kd']}  ADR={imp['adr']}  KAST={imp['kast']:.0%}")

    print(f"\nKills: {len(data['kills'])}  Damages: {len(data['damages'])}  "
          f"Grenades: {len(data['grenades'])}  Positions: {len(data['position_samples'])}")