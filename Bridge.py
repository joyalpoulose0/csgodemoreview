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


# ── build / run helpers ────────────────────────────────────────────────────────

def _go_available() -> bool:
    try:
        subprocess.run(["go", "version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def ensure_compiled(force: bool = False):
    if FORCE_GO_RUN:
        return None
    if not force and _BINARY.exists():
        src_mtime = (_GO_SRC / "parser_file.go").stat().st_mtime
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


# ── core bridge ────────────────────────────────────────────────────────────────

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


# ── internal helpers ───────────────────────────────────────────────────────────

def _round_index(data) -> dict:
    """rounds list → dict keyed by round number for O(1) lookup."""
    return {r["round"]: r for r in data.get("rounds", [])}


def _equip_type(val: int) -> str:
    if val < 2000:  return "eco"
    if val < 4500:  return "force"
    return "full"


def _killer_team(kill: dict) -> str:
    """
    Return the team label (TeamA/TeamB) of the killer directly from the kill event.
    The Go parser embeds killer_team / victim_team into every kill event, so no
    cross-referencing is needed here.
    """
    return kill.get("killer_team", "unknown")


def _victim_team(kill: dict) -> str:
    return kill.get("victim_team", "unknown")


# ── basic accessors ────────────────────────────────────────────────────────────

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


def get_round_events(data, round_num) -> dict:
    """All events (kills, damage, flashes, grenades, bomb) for a given round."""
    return {
        "round":       next((r for r in data.get("rounds", []) if r["round"] == round_num), None),
        "kills":       [k for k in data.get("kills", [])       if k["round"] == round_num],
        "damages":     [d for d in data.get("damages", [])     if d["round"] == round_num],
        "flashes":     [f for f in data.get("flashes", [])     if f["round"] == round_num],
        "grenades":    [g for g in data.get("grenades", [])    if g["round"] == round_num],
        "bomb_events": [b for b in data.get("bomb_events", []) if b["round"] == round_num],
    }


# ── round-level analytics ──────────────────────────────────────────────────────

def get_round_momentum(data) -> dict:
    """
    Per-round kill advantage by TEAM (TeamA / TeamB), not CT/T role.
    TeamA = started CT in round 1, TeamB = started T.
    Positive diff = TeamA dominated, negative = TeamB dominated.
    Kill team info comes directly from killer_team field in each kill event.
    """
    rounds = data.get("rounds", [])
    kills  = data.get("kills", [])

    kills_by_round: dict = defaultdict(lambda: {"TeamA": 0, "TeamB": 0})
    for k in kills:
        team = _killer_team(k)
        if team in ("TeamA", "TeamB"):
            kills_by_round[k["round"]][team] += 1

    momentum = {}
    for r in rounds:
        rnum = r["round"]
        a = kills_by_round[rnum]["TeamA"]
        b = kills_by_round[rnum]["TeamB"]
        momentum[rnum] = {"team_a_kills": a, "team_b_kills": b, "diff": a - b}

    return momentum


def get_round_win_streak(data) -> dict:
    """
    Longest consecutive win streak for TeamA and TeamB.
    Uses team_a_score / team_b_score from the Go output which are
    already halftime-corrected.
    """
    rounds = data.get("rounds", [])

    # Determine which team (A/B) won each round by cross-referencing
    # the CT/T winner with which team was CT that round (from kills).
    kills_by_round: dict = defaultdict(list)
    for k in data.get("kills", []):
        kills_by_round[k["round"]].append(k)

    a_streak = b_streak = 0
    a_best   = b_best   = 0

    for r in rounds:
        rnum   = r["round"]
        winner = r.get("winner", "")  # "CT" or "T"

        # find which team was CT this round from any kill event
        rk = kills_by_round.get(rnum, [])
        ct_team = "unknown"
        for k in rk:
            if k.get("killer_side") == "CT" and k.get("killer_team"):
                ct_team = k["killer_team"]
                break
            if k.get("victim_side") == "CT" and k.get("victim_team"):
                ct_team = k["victim_team"]
                break

        t_team = "TeamB" if ct_team == "TeamA" else "TeamA"
        winning_team = ct_team if winner == "CT" else t_team

        if winning_team == "TeamA":
            a_streak += 1
            b_streak  = 0
            a_best    = max(a_best, a_streak)
        elif winning_team == "TeamB":
            b_streak += 1
            a_streak  = 0
            b_best    = max(b_best, b_streak)

    return {"team_a_longest_streak": a_best, "team_b_longest_streak": b_best}


def get_opening_duel_stats(data) -> dict:
    """
    Per-round opening duel (first kill) win rates by TEAM.
    Uses killer_team / victim_team embedded directly in each kill event.
    """
    kills       = data.get("kills", [])
    entry_kills = [k for k in kills if k.get("is_entry")]

    a_wins = sum(1 for k in entry_kills if _killer_team(k) == "TeamA")
    b_wins = sum(1 for k in entry_kills if _killer_team(k) == "TeamB")
    total  = a_wins + b_wins

    return {
        "total_opening_duels": total,
        "team_a_wins":     a_wins,
        "team_b_wins":     b_wins,
        "team_a_win_rate": round(a_wins / total, 3) if total else 0,
        "team_b_win_rate": round(b_wins / total, 3) if total else 0,
        "by_round": [
            {
                "round":       k["round"],
                "winner_name": k["killer_name"],
                "winner_team": _killer_team(k),
                "winner_side": k["killer_side"],
                "victim_name": k["victim_name"],
                "weapon":      k["weapon"],
            }
            for k in entry_kills
        ],
    }


def detect_clutches(data) -> list:
    """
    Detect 1vX clutch situations per round.
    A clutch occurs when a player is the last alive on their team and
    gets at least one more kill. Tracks whether the clutch was won.
    """
    kills  = data.get("kills", [])
    rounds = data.get("rounds", [])
    clutches = []

    kills_by_round: dict = defaultdict(list)
    for k in kills:
        kills_by_round[k["round"]].append(k)

    for r in rounds:
        rnum = r["round"]
        rk   = sorted(kills_by_round[rnum], key=lambda x: x["tick"])

        ct_alive = t_alive = 5

        for i, k in enumerate(rk):
            # update alive counts
            if k["killer_side"] == "CT":
                t_alive -= 1
            else:
                ct_alive -= 1

            if ct_alive == 0 or t_alive == 0:
                break

            # check if victim's side is now at 1
            victim_side       = k["victim_side"]
            victim_side_alive = ct_alive if victim_side == "CT" else t_alive

            if victim_side_alive == 1:
                remaining = rk[i + 1:]
                clutch_kills = [ck for ck in remaining if ck["killer_side"] == victim_side]
                if clutch_kills:
                    opponents = t_alive if victim_side == "CT" else ct_alive
                    clutches.append({
                        "round":            rnum,
                        "player":           clutch_kills[0]["killer_name"],
                        "steam_id":         clutch_kills[0]["killer_steam_id"],
                        "team":             _killer_team(clutch_kills[0]),
                        "side":             victim_side,
                        "vs":               opponents + 1,
                        "kills_in_clutch":  len(clutch_kills),
                        "won":              r["winner"] == victim_side,
                    })
                break

    return clutches


def detect_comeback_rounds(data) -> list:
    """
    Rounds where the team with fewer kills still won.
    Uses team_a/team_b kill counts (halftime-correct) and maps
    the CT/T round winner back to the correct team via kill events.
    """
    momentum = get_round_momentum(data)
    rounds   = data.get("rounds", [])
    kills_by_round: dict = defaultdict(list)
    for k in data.get("kills", []):
        kills_by_round[k["round"]].append(k)

    comebacks = []
    for r in rounds:
        rnum   = r["round"]
        winner = r.get("winner", "")
        m      = momentum.get(rnum, {})
        a      = m.get("team_a_kills", 0)
        b      = m.get("team_b_kills", 0)

        # resolve CT/T winner to TeamA/TeamB
        rk = kills_by_round.get(rnum, [])
        ct_team = "unknown"
        for k in rk:
            if k.get("killer_side") == "CT" and k.get("killer_team"):
                ct_team = k["killer_team"]
                break
            if k.get("victim_side") == "CT" and k.get("victim_team"):
                ct_team = k["victim_team"]
                break
        t_team       = "TeamB" if ct_team == "TeamA" else "TeamA"
        winning_team = ct_team if winner == "CT" else t_team

        if a > b and winning_team == "TeamB":
            comebacks.append({"round": rnum, "winner": "TeamB",
                               "team_a_kills": a, "team_b_kills": b, "kill_deficit": a - b})
        elif b > a and winning_team == "TeamA":
            comebacks.append({"round": rnum, "winner": "TeamA",
                               "team_a_kills": a, "team_b_kills": b, "kill_deficit": b - a})

    return comebacks


def get_economy_efficiency(data) -> list:
    """
    Per-round buy type (eco / force / full) for each team and whether the
    lower-spending team won (upset).
    """
    rounds = data.get("rounds", [])
    result = []
    for r in rounds:
        ct_val  = r.get("ct_equip_value", 0)
        t_val   = r.get("t_equip_value", 0)
        winner  = r.get("winner", "")
        ct_type = _equip_type(ct_val)
        t_type  = _equip_type(t_val)
        upset   = (
            (ct_type in ("eco", "force") and t_type == "full" and winner == "CT") or
            (t_type  in ("eco", "force") and ct_type == "full" and winner == "T")
        )
        result.append({
            "round":       r["round"],
            "ct_equip":    ct_val,
            "t_equip":     t_val,
            "ct_buy_type": ct_type,
            "t_buy_type":  t_type,
            "winner":      winner,
            "upset":       upset,
        })
    return result


# ── player-level analytics ─────────────────────────────────────────────────────

def get_player_impact_score(data) -> dict:
    """
    HLTV-style impact rating. Weights entry kills, trade kills,
    flash assists, ADR, and multi-kill rounds.
    """
    players = data.get("player_summaries", [])
    kills   = data.get("kills", [])

    kills_by_player: dict = defaultdict(list)
    for k in kills:
        kills_by_player[str(k["killer_steam_id"])].append(k)

    impact = {}
    for p in players:
        sid = str(p["steam_id"])
        pk  = kills_by_player[sid]

        mk_by_round: dict = defaultdict(int)
        for k in pk:
            mk_by_round[k["round"]] += 1
        mk_bonus = sum(
            0.5 if v == 3 else 1.0 if v == 4 else 1.5
            for v in mk_by_round.values() if v >= 3
        )

        score = (
            len(pk)                     * 1.0 +
            p.get("entry_kills", 0)     * 1.5 +
            p.get("trade_kills", 0)     * 1.2 +
            p.get("flash_assists", 0)   * 0.5 +
            p.get("adr", 0)             * 0.01 +
            mk_bonus
        )

        impact[sid] = {
            "name":  p["name"],
            "team":  p.get("team", ""),
            "score": round(score, 2),
            "kd":    round(p["kills"] / max(p["deaths"], 1), 2),
            "adr":   round(p.get("adr", 0), 1),
            "kast":  round(p.get("kast", 0), 3),
        }

    return dict(sorted(impact.items(), key=lambda x: x[1]["score"], reverse=True))


def get_weapon_breakdown(data, steam_id=None) -> dict:
    """
    Kill count and headshot rate per weapon.
    Pass steam_id to filter to one player, or None for the whole match.
    """
    kills = data.get("kills", [])
    if steam_id:
        kills = [k for k in kills if str(k["killer_steam_id"]) == str(steam_id)]

    weapons: dict = defaultdict(lambda: {"kills": 0, "headshots": 0})
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


def get_damage_breakdown(data, steam_id=None) -> dict:
    """Damage dealt per hitgroup and per weapon."""
    damages = data.get("damages", [])
    if steam_id:
        damages = [d for d in damages if str(d["attacker_steam_id"]) == str(steam_id)]

    hitgroups: dict = defaultdict(int)
    by_weapon: dict = defaultdict(int)
    total = 0
    for d in damages:
        dmg = d.get("health_damage", 0)
        hitgroups[d.get("hit_group", "unknown")] += dmg
        by_weapon[d.get("weapon", "unknown")]    += dmg
        total += dmg

    return {
        "total_damage": total,
        "by_hitgroup":  dict(sorted(hitgroups.items(), key=lambda x: x[1], reverse=True)),
        "by_weapon":    dict(sorted(by_weapon.items(),  key=lambda x: x[1], reverse=True)),
    }


def get_utility_efficiency(data) -> dict:
    """
    Per-player grenade and flash efficiency.
    utility_damage / grenade counts HE + molotov damage only.
    flash_efficiency = enemies flashed / (enemies + teammates flashed).
    """
    grenades  = data.get("grenades", [])
    damages   = data.get("damages", [])
    flashes   = data.get("flashes", [])
    summaries = {str(p["steam_id"]): p for p in data.get("player_summaries", [])}

    util_weapons = {"HE Grenade", "Molotov", "Incendiary Grenade", "Inferno"}
    dmg_by_player:  dict = defaultdict(int)
    gren_by_player: dict = defaultdict(int)
    enemy_flashes:  dict = defaultdict(int)
    team_flashes:   dict = defaultdict(int)

    for d in damages:
        if d.get("weapon", "") in util_weapons:
            dmg_by_player[str(d["attacker_steam_id"])] += d.get("health_damage", 0)
    for g in grenades:
        gren_by_player[str(g["thrower_steam_id"])] += 1
    for f in flashes:
        sid = str(f["thrower_steam_id"])
        if f.get("is_team_flash"):
            team_flashes[sid]  += 1
        else:
            enemy_flashes[sid] += 1

    all_sids = set(dmg_by_player) | set(gren_by_player) | set(enemy_flashes)
    result = {}
    for sid in all_sids:
        ngren = gren_by_player.get(sid, 0)
        ndmg  = dmg_by_player.get(sid, 0)
        nef   = enemy_flashes.get(sid, 0)
        ntf   = team_flashes.get(sid, 0)
        result[sid] = {
            "name":               summaries.get(sid, {}).get("name", sid),
            "team":               summaries.get(sid, {}).get("team", ""),
            "grenades_thrown":    ngren,
            "utility_damage":     ndmg,
            "damage_per_grenade": round(ndmg / ngren, 2) if ngren else 0,
            "enemies_flashed":    nef,
            "team_flashes":       ntf,
            "flash_efficiency":   round(nef / (nef + ntf), 3) if (nef + ntf) else 0,
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["utility_damage"], reverse=True))


def get_survival_analysis(data) -> dict:
    """
    Per-player survival rate, avg time of death, and traded-death rate.
    """
    player_rounds = data.get("player_rounds", {})
    kills         = data.get("kills", [])
    rounds        = _round_index(data)
    tick_rate     = max(data.get("tick_rate", 64), 1)
    summaries     = {str(p["steam_id"]): p for p in data.get("player_summaries", [])}

    deaths_by_player: dict = defaultdict(list)
    for k in kills:
        deaths_by_player[str(k["victim_steam_id"])].append(k)

    result = {}
    for sid, rds in player_rounds.items():
        p        = summaries.get(sid, {})
        survived = sum(1 for r in rds if r.get("survived"))
        total    = len(rds)
        deaths   = deaths_by_player.get(sid, [])

        death_times = []
        for d in deaths:
            r = rounds.get(d["round"])
            if r:
                death_times.append((d["tick"] - r["start_tick"]) / tick_rate)

        traded = sum(1 for d in deaths if d.get("is_trade"))
        result[sid] = {
            "name":             p.get("name", sid),
            "team":             p.get("team", ""),
            "rounds_played":    total,
            "survived":         survived,
            "survival_rate":    round(survived / total, 3) if total else 0,
            "deaths":           len(deaths),
            "traded_deaths":    traded,
            "trade_rate":       round(traded / len(deaths), 3) if deaths else 0,
            "avg_death_time_s": round(sum(death_times) / len(death_times), 1) if death_times else None,
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["survival_rate"], reverse=True))


def get_kill_distance_analysis(data, steam_id=None) -> dict:
    """
    Average, median, and max kill distance per player in CS2 world units.
    (1 unit ≈ 0.75 inches / ~1.9 cm)
    """
    kills = data.get("kills", [])
    if steam_id:
        kills = [k for k in kills if str(k["killer_steam_id"]) == str(steam_id)]

    by_player: dict = defaultdict(list)
    for k in kills:
        kp = k.get("killer_pos", {})
        vp = k.get("victim_pos", {})
        if kp and vp:
            dx   = kp.get("x", 0) - vp.get("x", 0)
            dy   = kp.get("y", 0) - vp.get("y", 0)
            dist = math.sqrt(dx * dx + dy * dy)
            by_player[str(k["killer_steam_id"])].append(dist)

    summaries = {str(p["steam_id"]): p for p in data.get("player_summaries", [])}
    result = {}
    for sid, dists in by_player.items():
        dists.sort()
        n = len(dists)
        p = summaries.get(sid, {})
        result[sid] = {
            "name":     p.get("name", sid),
            "team":     p.get("team", ""),
            "kills":    n,
            "avg_dist": round(sum(dists) / n, 1) if n else 0,
            "med_dist": round(dists[n // 2], 1)  if n else 0,
            "max_dist": round(max(dists), 1)      if n else 0,
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["avg_dist"], reverse=True))


def get_flash_analysis(data) -> dict:
    """
    Per-player flash stats: enemies blinded, avg duration, team flash count,
    best single flash duration, and overall flash efficiency.
    """
    flashes   = data.get("flashes", [])
    summaries = {str(p["steam_id"]): p for p in data.get("player_summaries", [])}

    by_thrower: dict = defaultdict(lambda: {
        "enemy_flashes": 0, "team_flashes": 0,
        "total_enemy_dur": 0.0, "top_flash": 0.0,
    })

    for f in flashes:
        sid = str(f["thrower_steam_id"])
        dur = f.get("duration_seconds", 0)
        if f.get("is_team_flash"):
            by_thrower[sid]["team_flashes"] += 1
        else:
            by_thrower[sid]["enemy_flashes"]   += 1
            by_thrower[sid]["total_enemy_dur"]  += dur
            by_thrower[sid]["top_flash"]         = max(by_thrower[sid]["top_flash"], dur)

    result = {}
    for sid, v in by_thrower.items():
        nef = v["enemy_flashes"]
        p   = summaries.get(sid, {})
        result[sid] = {
            "name":             p.get("name", sid),
            "team":             p.get("team", ""),
            "enemy_flashes":    nef,
            "team_flashes":     v["team_flashes"],
            "avg_duration_s":   round(v["total_enemy_dur"] / nef, 2) if nef else 0,
            "best_flash_s":     round(v["top_flash"], 2),
            "flash_efficiency": round(nef / max(nef + v["team_flashes"], 1), 3),
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["enemy_flashes"], reverse=True))


def get_bomb_stats(data) -> dict:
    """Bomb plant / defuse / explode summary per player and site."""
    bomb_events = data.get("bomb_events", [])

    plants   = [b for b in bomb_events if b["event_type"] == "planted"]
    defuses  = [b for b in bomb_events if b["event_type"] == "defused"]
    explodes = [b for b in bomb_events if b["event_type"] == "exploded"]

    plants_by_player:  dict = defaultdict(int)
    defuses_by_player: dict = defaultdict(int)
    plants_by_site:    dict = defaultdict(int)

    for b in plants:
        plants_by_player[b.get("player_name", "?")] += 1
        plants_by_site[b.get("site", "?")]           += 1
    for b in defuses:
        defuses_by_player[b.get("player_name", "?")] += 1

    return {
        "total_plants":     len(plants),
        "total_defuses":    len(defuses),
        "total_explosions": len(explodes),
        "defuse_rate":      round(len(defuses) / len(plants), 3) if plants else 0,
        "plants_by_site":   dict(plants_by_site),
        "top_planters":     dict(sorted(plants_by_player.items(),  key=lambda x: x[1], reverse=True)),
        "top_defusers":     dict(sorted(defuses_by_player.items(), key=lambda x: x[1], reverse=True)),
    }


def get_heatmap_points(data, steam_id=None, alive_only=True) -> list:
    """
    (x, y) position tuples for heatmap plotting, sampled every 32 ticks.
    alive_only=True skips dead-player positions (default).
    """
    positions = data.get("position_samples", [])
    if steam_id:
        positions = [p for p in positions if str(p["steam_id"]) == str(steam_id)]
    if alive_only:
        positions = [p for p in positions if p.get("is_alive")]
    points = []
    for p in positions:
        pos = p.get("pos", {})
        x, y = pos.get("x"), pos.get("y")
        if x is not None and y is not None:
            points.append((x, y))
    return points


def get_death_heatmap_points(data, steam_id=None) -> list:
    """
    (x, y) victim positions for death heatmaps.
    Skips zero-position events (player not yet spawned).
    """
    kills = data.get("kills", [])
    if steam_id:
        kills = [k for k in kills if str(k["victim_steam_id"]) == str(steam_id)]
    points = []
    for k in kills:
        vp = k.get("victim_pos", {})
        x, y = vp.get("x"), vp.get("y")
        if x is not None and y is not None and (x != 0 or y != 0):
            points.append((x, y))
    return points


# ── full analytics bundle ──────────────────────────────────────────────────────

def generate_full_analytics(data) -> dict:
    """Run all analytics and return a single dict for the AI coaching layer."""
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


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python parse_demo.py <demo.dem> [output.json]")
        sys.exit(1)

    demo = sys.argv[1]
    out  = sys.argv[2] if len(sys.argv) >= 3 else None
    data = parse_demo(demo, out)

    print(f"\n=== {data['map_name']} | {data['total_rounds']} rounds ===")
    print(f"    TeamA {data.get('team_a_score', '?')} – {data.get('team_b_score', '?')} TeamB")
    print(f"    (CT {data['ct_score']} – {data['t_score']} T role-based)\n")

    print("── Player Summaries ──────────────────────────────────────────")
    for ps in data["player_summaries"]:
        kd = ps["kills"] / max(ps["deaths"], 1)
        print(f"  [{ps.get('team','?'):5s}] {ps['name']:20s}  "
              f"K/D={kd:.2f}  ADR={ps['adr']:.1f}  KAST={ps['kast']:.0%}  "
              f"HS={ps['headshots']}  Entry={ps['entry_kills']}  Trade={ps['trade_kills']}")

    analytics = generate_full_analytics(data)

    print("\n── Opening Duel Win Rates ────────────────────────────────────")
    od = analytics["opening_duels"]
    print(f"  TeamA: {od['team_a_win_rate']:.0%}  TeamB: {od['team_b_win_rate']:.0%}"
          f"  ({od['total_opening_duels']} duels)")

    print("\n── Clutches ──────────────────────────────────────────────────")
    for c in analytics["clutches"]:
        won = "WON" if c["won"] else "LOST"
        print(f"  R{c['round']:>2}  [{c['team']:5s}] {c['player']:20s}"
              f"  1v{c['vs']}  {c['kills_in_clutch']}K  {won}")

    print("\n── Bomb Stats ────────────────────────────────────────────────")
    bs = analytics["bomb_stats"]
    print(f"  Plants: {bs['total_plants']}  Defuses: {bs['total_defuses']}  "
          f"Explosions: {bs['total_explosions']}  Defuse rate: {bs['defuse_rate']:.0%}")
    print(f"  By site: {bs['plants_by_site']}")

    print("\n── Impact Scores ─────────────────────────────────────────────")
    for sid, imp in analytics["impact"].items():
        print(f"  [{imp['team']:5s}] {imp['name']:20s}  score={imp['score']:.2f}"
              f"  K/D={imp['kd']}  ADR={imp['adr']}  KAST={imp['kast']:.0%}")

    ws = analytics["win_streaks"]
    print(f"\n── Win Streaks ───────────────────────────────────────────────")
    print(f"  TeamA best: {ws['team_a_longest_streak']}  "
          f"TeamB best: {ws['team_b_longest_streak']}")

    print(f"\nKills: {len(data['kills'])}  Damages: {len(data['damages'])}  "
          f"Grenades: {len(data['grenades'])}  Positions: {len(data['position_samples'])}")
