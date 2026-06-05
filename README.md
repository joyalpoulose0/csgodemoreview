# CS2 Demo Review

A CS2 (Counter-Strike 2) demo analysis system built with Go + Python that parses `.dem` files, extracts detailed match events and computes performance metrics. Moreover, I have integrated LLMs to provide feedback to user on their demo.

---

Summary: 

This project parses CS2 demo files and converts raw match data into structured analytics, including:
In game Events such as:
- Kills (killer/victim, weapon, headshot, wallbang, noscope, smoke kills, flash blind kills)
- Damage per hit (health + armor, hit groups, weapons)
- Flashes (thrower, victim, duration, team flashes)
- Grenades (type, thrower, position, detonation)
- Bomb events (plant, defuse, explode, site tracking)
- Round events (start/end tick, winner, reason, economy values)
- Player positions (sampled every 32 ticks)

It then computes performance metrics such as:
Per player:
- K/D, KDA
- ADR (Average Damage per Round)
- KAST (Kill / Assist / Survive / Trade)
- Headshot %
- Entry kill rate & opening duel win rate
- Trade kill / trade death rate
- Multi-kill rounds (3K / 4K / 5K)
- Survival rate
- Average kill distance
- Utility usage (grenades per round)
- Flash impact (enemies flashed, duration, team flashes)
- Hitgroup distribution
- Weapon kill breakdown
- Damage consistency score

I have used Go for parsing demos using demoinfocs-golang (github.com/markus-wa/demoinfocs-golang) and Python for feature engineering and computation. After a short break, I have implemented AI powered coaching feedback using LLMs.

How it works: 
1. Load `.dem` file
2. Go parser extracts raw match events
3. JSON output generated
4. Python computes advanced features
5. LLM generates coaching report

Expected Output: Full structured match JSON (.json file), Player-level analytics. 
To turn raw CS2 demo data into actionable coaching insights for players improving aim, positioning, and game sense.
