"""
coach.py
────────
Two-stage feedback:
  1. Rule-based insights (deterministic, fast, free)
  2. LLM analysis (richer, uses rules as context)

Combine both for best output.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

client = OpenAI()  # Not yet setup

# Rule based insights
def rule_based_insights(pf: dict) -> list[dict]:
    """
    Returns a list of insight dicts:
      { "category": str, "severity": "good"|"warn"|"bad", "message": str }
    """
    insights = []
    add = insights.append

    kd = pf.get("kd_ratio", 1)
    adr = pf.get("adr", 0)
    hs = pf.get("hs_percent", 0)
    kast = pf.get("kast", 0)
    survival = pf.get("survival_rate", 0)
    entry_rate = pf.get("entry_kill_rate", 0)
    opening_wr = pf.get("opening_duel_win_rate", 0.5)
    trade_kills = pf.get("trade_kills", 0)
    traded_deaths = pf.get("traded_deaths", 0)
    mk3 = pf.get("multi_kills_3", 0)
    team_flashes = pf.get("team_flashes", 0)
    enemies_flashed_pr = pf.get("enemies_flashed_per_round", 0)
    flash_dur = pf.get("avg_flash_duration_s", 0)
    util_pr = pf.get("grenades_per_round", 0)
    consistency = pf.get("damage_consistency_score", 0)
    avg_dist = pf.get("avg_kill_distance_units", 0)
    rounds = pf.get("rounds_played", 1)

    # Aim
    if hs >= 0.55:
        add({"category": "aim", "severity": "good",
             "message": f"Elite headshot rate ({hs:.0%}) — your crosshair placement is strong."})
    elif hs >= 0.40:
        add({"category": "aim", "severity": "good",
             "message": f"Good headshot rate ({hs:.0%})."})
    elif hs < 0.25:
        add({"category": "aim", "severity": "bad",
             "message": f"Low headshot rate ({hs:.0%}). Focus on crosshair placement at head height."})

    # Duel rate
    if kd >= 1.5:
        add({"category": "dueling", "severity": "good",
             "message": f"Strong K/D ({kd:.2f}) — you're winning most engagements."})
    elif kd < 0.8:
        add({"category": "dueling", "severity": "bad",
             "message": f"K/D below 1 ({kd:.2f}). You're losing more duels than you're winning. "
                        "Review your peek timings and crosshair placement."})

    # Impact
    if adr >= 85:
        add({"category": "impact", "severity": "good",
             "message": f"High ADR ({adr:.1f}) — you deal consistent damage every round."})
    elif adr < 60:
        add({"category": "impact", "severity": "bad",
             "message": f"Low ADR ({adr:.1f}). You're not dealing enough damage. "
                        "Prioritise taking damage-efficient duels over passive play."})

    # consistency
    if consistency < 0.4:
        add({"category": "consistency", "severity": "good",
             "message": "Very consistent damage output across rounds."})
    elif consistency > 0.8:
        add({"category": "consistency", "severity": "warn",
             "message": "Highly variable damage output — you have explosive rounds but also "
                        "dead rounds. Try to stay impactful even in tough rounds."})

    # KAST
    if kast >= 0.75:
        add({"category": "impact", "severity": "good",
             "message": f"KAST {kast:.0%} — you contribute positively in most rounds."})
    elif kast < 0.55:
        add({"category": "impact", "severity": "bad",
             "message": f"KAST {kast:.0%} is below average. In rounds where you don't get kills, "
                        "focus on assists, trading, or at minimum surviving."})

    # Entry Duel
    if opening_wr >= 0.6 and entry_rate >= 0.3:
        add({"category": "opening_duels", "severity": "good",
             "message": f"Winning {opening_wr:.0%} of opening duels at a rate of {entry_rate:.0%}/round — "
                        "you're an effective entry fragger."})
    elif opening_wr < 0.4 and entry_rate >= 0.3:
        add({"category": "opening_duels", "severity": "bad",
             "message": f"You take a lot of opening duels ({entry_rate:.0%}/round) "
                        f"but only win {opening_wr:.0%}. Consider more support/setup plays "
                        "or improve pre-aim before peeking."})

    # Trading
    trade_rate = traded_deaths / max(pf.get("deaths", 1), 1)
    if trade_rate >= 0.5:
        add({"category": "trading", "severity": "good",
             "message": f"{trade_rate:.0%} of your deaths were traded — your team recovers well "
                        "from your deaths."})
    elif trade_rate < 0.2 and pf.get("deaths", 0) > 5:
        add({"category": "trading", "severity": "warn",
             "message": "Low trade rate on your deaths. Your team isn't converting your deaths into value. "
                        "Communicate and bait/trade more deliberately."})

    # Multi Kills
    if mk3 > 0:
        add({"category": "clutch", "severity": "good",
             "message": f"{mk3} round(s) with 3+ kills — strong clutch/pop-off potential."})

    # Survival
    if survival < 0.25:
        add({"category": "survival", "severity": "bad",
             "message": f"Low survival rate ({survival:.0%}). You're dying too early each round. "
                        "Play for information before committing, and avoid wide peeks without support."})

    # Utility
    if team_flashes > 3:
        add({"category": "utility", "severity": "bad",
             "message": f"{team_flashes} team flashes this match. "
                        "Check your lineup timings and communicate flash calls."})

    if util_pr < 0.5:
        add({"category": "utility", "severity": "warn",
             "message": f"Low utility usage ({util_pr:.1f} grenades/round). "
                        "Buy and use grenades every round — smokes, flashes, and molotovs are free value."})
    elif util_pr >= 1.5:
        add({"category": "utility", "severity": "good",
             "message": f"High utility usage ({util_pr:.1f}/round) — strong grenade economy."})

    if enemies_flashed_pr >= 1.0:
        add({"category": "utility", "severity": "good",
             "message": f"Flashing {enemies_flashed_pr:.1f} enemies/round — great flash support."})

    if flash_dur < 1.0 and enemies_flashed_pr >= 0.5:
        add({"category": "utility", "severity": "warn",
             "message": f"Short average flash duration ({flash_dur:.1f}s). "
                        "Use better pop-flash lineups to blind enemies for longer."})

    # Kill Distance
    if avg_dist > 1200:
        add({"category": "aim", "severity": "good",
             "message": f"High average kill distance ({avg_dist:.0f} units) — comfortable at range."})
    elif avg_dist < 400:
        add({"category": "playstyle", "severity": "warn",
             "message": f"Most kills at very close range ({avg_dist:.0f} units). "
                        "You may be over-relying on close angles. Practice mid-range duels."})

    return insights


# LLM Feedback

def generate_feedback(
    pf: dict,
    insights: list[dict] | None = None,
    model: str = "gpt-4.1-mini", # Not yet setup
) -> str:
    """
    Generate AI coaching feedback for a player.

    pf       : player feature dict from compute.py
    insights : pre-computed rule-based insights (optional, will compute if None)
    model    : OpenAI model to use
    """
    if insights is None:
        insights = rule_based_insights(pf)

    insight_lines = "\n".join(
        f"  [{i['severity'].upper()}] {i['category']}: {i['message']}"
        for i in insights
    )

    weapon_str = ", ".join(
        f"{w}: {c}" for w, c in list(pf.get("weapon_kills", {}).items())[:5]
    )
    hitgroup_str = ", ".join(
        f"{hg}: {c}" for hg, c in pf.get("hitgroup_distribution", {}).items()
    )

    prompt = f"""You are an elite CS2 coach reviewing a player's performance data.
Analyse the stats below and write targeted, actionable coaching feedback.

=== PLAYER: {pf.get("name", "Unknown")} ===
Rounds played:     {pf.get("rounds_played", 0)}
K/D:               {pf.get("kd_ratio", 0):.2f}
KDA:               {pf.get("kda", 0):.2f}
ADR:               {pf.get("adr", 0):.1f}
KAST:              {pf.get("kast", 0):.0%}
HS%:               {pf.get("hs_percent", 0):.0%}
Kills/round:       {pf.get("kills_per_round", 0):.2f}
Survival rate:     {pf.get("survival_rate", 0):.0%}
Entry kills:       {pf.get("entry_kills", 0)} ({pf.get("entry_kill_rate", 0):.0%}/round)
Opening duel WR:   {pf.get("opening_duel_win_rate", 0):.0%}
Trade kills:       {pf.get("trade_kills", 0)}
Traded deaths:     {pf.get("traded_deaths", 0)}
3K rounds:         {pf.get("multi_kills_3", 0)}
4K rounds:         {pf.get("multi_kills_4", 0)}
5K rounds:         {pf.get("multi_kills_5", 0)}
Avg kill distance: {pf.get("avg_kill_distance_units", 0):.0f} units
Wallbangs:         {pf.get("wallbangs", 0)}
Damage consistency (CV, lower=better): {pf.get("damage_consistency_score", 0):.2f}
Grenades/round:    {pf.get("grenades_per_round", 0):.2f}
Enemies flashed/round: {pf.get("enemies_flashed_per_round", 0):.2f}
Avg flash duration: {pf.get("avg_flash_duration_s", 0):.1f}s
Team flashes:      {pf.get("team_flashes", 0)}
Top weapons:       {weapon_str or "n/a"}
Hit distribution:  {hitgroup_str or "n/a"}

=== PRE-COMPUTED INSIGHTS ===
{insight_lines or "  (none generated)"}

=== YOUR TASK ===
Write 3–5 coaching points. For each:
- Name the specific problem or strength
- Explain WHY it matters in CS2
- Give a concrete drill or habit to fix/reinforce it

Be direct and specific. Reference the actual numbers above.
Do NOT be generic ("improve your aim"). 
Format as a numbered list. Keep it under 400 words total.
"""

    response = client.chat.completions.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# Combined-

def analyze_player(features: dict, target_steam_id: str | None = None) -> dict:
    """
    Full analysis pipeline for a single player.
    Returns both rule-based insights and LLM feedback.
    """
    if target_steam_id:
        pf = features.get("players", {}).get(target_steam_id)
    else:
        # default to first player in summaries
        players = features.get("players", {})
        pf = next(iter(players.values()), None) if players else None

    if pf is None:
        return {"error": "Player not found in features"}

    insights = rule_based_insights(pf)
    feedback = generate_feedback(pf, insights)

    return {
        "player": pf.get("name"),
        "steam_id": pf.get("steam_id"),
        "insights": insights,
        "ai_feedback": feedback,
        "key_stats": {
            "kd_ratio": pf.get("kd_ratio"),
            "adr": pf.get("adr"),
            "kast": pf.get("kast"),
            "hs_percent": pf.get("hs_percent"),
            "survival_rate": pf.get("survival_rate"),
            "entry_kill_rate": pf.get("entry_kill_rate"),
            "opening_duel_win_rate": pf.get("opening_duel_win_rate"),
            "grenades_per_round": pf.get("grenades_per_round"),
        },
    }