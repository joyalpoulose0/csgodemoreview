"""
Python bridge to the Go parser.
Flow:
  upload a .dem file, it is parsed by Go parser which outputs a JSON file that is used by this Python bridge for further data analysis
  (.dem file → Go parser → JSON file → Python dict)
"""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
_GO_SRC = _HERE / "parser_file"
_BINARY_NAME = "cs2parser.exe" if platform.system() == "Windows" else "cs2parser"
_BINARY = _GO_SRC / _BINARY_NAME

# Set to True to always use `go run` (skips compiled binary entirely)
FORCE_GO_RUN = False

# Block detection
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

# Build manager, uses precompiled parser else executes and run
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

# Checking for any blocks by Windows
def _is_blocked(result: subprocess.CompletedProcess) -> bool:
    combined = (result.stdout or "") + (result.stderr or "")
    return result.returncode != 0 and any(s in combined for s in _BLOCK_SIGNALS)

# Runs parser file
def _run_binary(binary, demo_path, out_path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), str(demo_path), str(out_path)],
        capture_output=True, text=True,
    )

# Backup paser_file if compiled binary is unavailable
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

# Check output for any errors
def _check_result(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"Parser exited {result.returncode}:\n"
            f"stdout: {(result.stdout or '')[:2000]}\n"
            f"stderr: {(result.stderr or '')[:2000]}"
        )

# Core python bridge code, parses a demo file and returns a python dict
def parse_demo(demo_path, output_path=None) -> dict:
    demo_path = Path(demo_path).resolve()

    # Check for demo
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
                print("[parser] binary blocked by Application Control -- falling back to 'go run'") # Check for blocks
                result = _run_go_run(demo_path, out_path)
        else:
            result = _run_go_run(demo_path, out_path)

        _check_result(result)
        return json.loads(out_path.read_text(encoding="utf-8"))

    finally:
        if use_tmp:
            out_path.unlink(missing_ok=True)

# Get player Summary
def get_player_summary(data, steam_id=None, name=None):
    for ps in data.get("player_summaries", []):
        if steam_id is not None and str(ps["steam_id"]) == str(steam_id):
            return ps
        if name is not None and ps["name"].lower() == name.lower():
            return ps
    return None

# Get all instances of player's kills
def get_player_kills(data, steam_id):
    sid = str(steam_id)
    return [k for k in data.get("kills", []) if str(k["killer_steam_id"]) == sid]

# Get all instances of player's deaths
def get_player_deaths(data, steam_id):
    sid = str(steam_id)
    return [k for k in data.get("kills", []) if str(k["victim_steam_id"]) == sid]

# Get all instances of player's position when an event is triggered
def get_player_positions(data, steam_id):
    sid = str(steam_id)
    return [p for p in data.get("position_samples", []) if str(p["steam_id"]) == sid]

# Get all events in a round
def get_round_events(data, round_num):
    return {
        "round": next((r for r in data.get("rounds", []) if r["round"] == round_num), None),
        "kills": [k for k in data.get("kills", []) if k["round"] == round_num],
        "damages": [d for d in data.get("damages", []) if d["round"] == round_num],
        "flashes": [f for f in data.get("flashes", []) if f["round"] == round_num],
        "grenades": [g for g in data.get("grenades", []) if g["round"] == round_num],
        "bomb_events": [b for b in data.get("bomb_events", []) if b["round"] == round_num],
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python parse_demo.py <demo.dem> [output.json]")
        sys.exit(1)

    demo = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else None
    data = parse_demo(demo, out)

    print(f"\n=== {data['map_name']} | {data['total_rounds']} rounds | "
          f"CT {data['ct_score']} - {data['t_score']} T ===\n")
    for ps in data["player_summaries"]:
        kd = ps["kills"] / max(ps["deaths"], 1)
        print(f"  {ps['name']:20s}  K/D={kd:.2f}  ADR={ps['adr']:.1f}  "
              f"KAST={ps['kast']:.0%}  HS={ps['headshots']}  "
              f"Entry={ps['entry_kills']}  Trade={ps['trade_kills']}")
    print(f"\nKills: {len(data['kills'])}  Damages: {len(data['damages'])}  "
          f"Grenades: {len(data['grenades'])}  Positions: {len(data['position_samples'])}")