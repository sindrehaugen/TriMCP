#!/usr/bin/env python3
"""
phase6-runners/wave-sync.py
────────────────────────────
Utility: check wave completion status in to-do-v1-phase6.md.

Usage:
    python phase6-runners/wave-sync.py           # Wave 1 check only
    python phase6-runners/wave-sync.py --all     # All 19 tasks
    python phase6-runners/wave-sync.py --watch   # Poll every 15s until Wave 1 done
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TODO_FILE    = PROJECT_ROOT / "to-do-v1-phase6.md"

# All tasks: (wave_label, task_id, fix_ids, tool)
ALL_TASKS: list[tuple[str, str, list[str], str]] = [
    ("W1", "W1-A", ["FIX-013"], "Haiku"),
    ("W1", "W1-B", ["FIX-020"], "Composer"),
    ("W2", "W2-A", ["FIX-025"], "Composer"),
    ("W2", "W2-B", ["FIX-026"], "Composer"),
    ("W2", "W2-C", ["FIX-027"], "Gemini Pro"),
    ("W2", "W2-D", ["FIX-029"], "Composer"),
    ("W3", "W3-A", ["FIX-030"], "Gemini Pro"),
    ("W3", "W3-B", ["FIX-031"], "Haiku"),
    ("W3", "W3-C", ["FIX-032"], "Composer"),
    ("W3", "W3-D", ["FIX-038"], "Haiku"),
    ("W3", "W3-E", ["FIX-039"], "Haiku"),
    ("W3", "W3-F", ["FIX-040"], "Gemini Pro"),
    ("W3", "W3-G", ["FIX-041"], "Composer"),
    ("W4", "W4-A", ["FIX-051"], "Haiku"),
    ("W4", "W4-B", ["FIX-052"], "Haiku"),
    ("W4", "W4-C", ["FIX-053"], "Haiku"),
    ("W4", "W4-D", ["FIX-054", "FIX-055"], "Flash"),
    ("W4", "W4-E", ["FIX-057"], "Gemini Pro"),
    ("W4", "W4-F", ["FIX-046"], "Composer"),
]

WAVE1_FIXES = ["FIX-013", "FIX-020"]


def _todo_text() -> str:
    return TODO_FILE.read_text(encoding="utf-8")


def fix_status(fix_id: str, text: str) -> tuple[bool, str]:
    """
    Returns (completed: bool, date_or_status: str).

    Uses ^id: (re.MULTILINE) to skip indented list entries in the DISPATCH MAP
    section (e.g. `  - id: FIX-013`) which would otherwise shadow the real block.
    """
    pattern = rf"^id:\s*{re.escape(fix_id)}\b(.*?)(?=\n```|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    if not match:
        return False, "NOT FOUND IN TODO"
    block = match.group(0)
    date_match = re.search(r"completed:\s*(\S+)", block)
    if date_match:
        return True, date_match.group(1)
    # Check if dispatched
    if re.search(r"dispatched:\s*yes", block):
        return False, "dispatched (not completed)"
    return False, "pending"


def print_status(show_all: bool = False) -> dict[str, bool]:
    """Print status table. Returns {fix_id: completed} for Wave 1."""
    text = _todo_text()
    tasks_to_show = ALL_TASKS if show_all else [t for t in ALL_TASKS if t[0] == "W1"]

    wave1_results: dict[str, bool] = {}
    prev_wave = None

    for wave, task_id, fix_ids, tool in tasks_to_show:
        if wave != prev_wave:
            print(f"\n  -- Wave {wave[-1]} ----------------------------------")
            prev_wave = wave

        for fix_id in fix_ids:
            done, info = fix_status(fix_id, text)
            icon = "[x]" if done else "[ ]"
            status_str = info if done else f"  {info}"
            print(f"  {icon}  {task_id:<6} {fix_id:<10} {tool:<12} {status_str}")
            if fix_id in WAVE1_FIXES:
                wave1_results[fix_id] = done

    return wave1_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave completion status checker")
    parser.add_argument("--all",   action="store_true", help="Show all 19 tasks")
    parser.add_argument("--watch", action="store_true", help="Poll every 15s until Wave 1 done")
    args = parser.parse_args()

    print()
    print("  TriMCP Phase 6 — Wave Sync Status")
    print(f"  State file: {TODO_FILE.name}")
    print()

    if args.watch:
        print("  Watching for Wave 1 completion (Ctrl+C to stop)...")
        while True:
            wave1 = print_status(show_all=False)
            all_done = all(wave1.values())
            if all_done:
                print("\n  WAVE 1 COMPLETE All agents may proceed.\n")
                return 0
            missing = [k for k, v in wave1.items() if not v]
            print(f"\n  Waiting for: {', '.join(missing)}  (retrying in 15s)\n")
            time.sleep(15)
    else:
        wave1 = print_status(show_all=args.all)
        print()

        if all(wave1.values()):
            print("  WAVE 1 COMPLETE All agents may proceed.\n")
            return 0
        else:
            missing = [k for k, v in wave1.items() if not v]
            print(f"  WAVE 1 PENDING - missing: {', '.join(missing)}\n")
            return 1


if __name__ == "__main__":
    sys.exit(main())
