#!/usr/bin/env python3
"""
phase6-runners/gemini-pro-runner.py
────────────────────────────────────
Autonomous Phase 6 remediation runner for Gemini 3.1 Pro (Gemini CLI).

Reads task definitions from phase6-supplemental-sequences.md.
Tracks state in to-do-v1-phase6.md.
Calls `gemini -p "..." -y` for each assigned task in wave order.

Usage:
    cd C:\\Users\\SindreLøvlieHaugen\\Documents\\systemer\\TriMCP\\TriMCP-1
    python phase6-runners/gemini-pro-runner.py

Options:
    --dry-run    Print prompts without calling gemini
    --skip-sync  Skip Wave 1 completion check (for testing)
    --task W2-C  Run a single named task only
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────

PROJECT_ROOT   = Path(__file__).parent.parent.resolve()
TODO_FILE      = PROJECT_ROOT / "to-do-v1-phase6.md"
SEQUENCES_FILE = PROJECT_ROOT / "phase6-supplemental-sequences.md"

# ──────────────────────────────────────────────────────────────────
# Task definitions for Gemini Pro
# Each entry: (wave_task_id, fix_id, section_header_fragment, description)
# ──────────────────────────────────────────────────────────────────

TASKS: list[tuple[str, str, str, str]] = [
    (
        "W2-C", "FIX-027",
        "W2-C · FIX-027",
        "garbage_collector.py - OFFSET to keyset pagination",
    ),
    (
        "W3-A", "FIX-030",
        "W3-A · FIX-030",
        "graph_query.py - BFS cycle guard CTE path accumulator",
    ),
    (
        "W3-F", "FIX-040",
        "W3-F · FIX-040",
        "orchestrators/migration.py - TOCTOU to atomic INSERT",
    ),
    (
        "W4-E", "FIX-057",
        "W4-E · FIX-057",
        "fargate-worker/main.tf - ECS autoscaling resources",
    ),
]

WAVE1_DEPENDENCIES = ["FIX-013", "FIX-020"]  # must both be complete before we start

GEMINI_MODEL = "gemini-2.5-pro"

# ──────────────────────────────────────────────────────────────────
# State helpers
# ──────────────────────────────────────────────────────────────────

def _todo_text() -> str:
    return TODO_FILE.read_text(encoding="utf-8")


def is_fix_completed(fix_id: str) -> bool:
    """Return True if the standalone FIX YAML block contains a `completed:` field.

    Uses ^id: anchored to line-start (re.MULTILINE) so that indented list
    entries like `  - id: FIX-013` inside the DISPATCH MAP section are skipped.
    Those entries never have a `completed:` field and caused false-negative results
    when re.search found them before the real fix block.
    """
    text = _todo_text()
    pattern = rf"^id:\s*{re.escape(fix_id)}\b(.*?)(?=\n```|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    if not match:
        return False
    block = match.group(0)
    return bool(re.search(r"completed:", block))


def mark_fix_completed(fix_id: str, task_id: str, date: str = "2026-05-12") -> None:
    """
    Update the standalone FIX YAML block in the todo file.

    Anchors to ^id: (line-start) so that indented list entries in the
    DISPATCH MAP section are never matched in place of the real fix block.
    """
    text = _todo_text()

    # Find the standalone block using the same anchor as is_fix_completed
    pattern = rf"^id:\s*{re.escape(fix_id)}\b"
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        print(f"  [WARN] Could not find standalone block for {fix_id} in todo file.", file=sys.stderr)
        return
    block_start = m.start()

    # Find the end of this YAML block (next ``` or EOF)
    block_end = text.find("\n```", block_start)
    if block_end == -1:
        block_end = len(text)
    else:
        block_end = block_end + 1  # include the newline before ```

    block = text[block_start:block_end]

    # Update dispatched
    block = re.sub(r"dispatched:\s*NO", "dispatched: yes", block)
    block = re.sub(r"dispatched_by:\s*NONE[^\n]*", f"dispatched_by: {task_id}", block)

    # Add completed: if not already present
    if "completed:" not in block:
        block = re.sub(
            r"(dispatched_by:[^\n]*\n)",
            rf"\1completed: {date}\n",
            block,
        )

    new_text = text[:block_start] + block + text[block_end:]
    TODO_FILE.write_text(new_text, encoding="utf-8")
    print(f"  [TODO] {fix_id} marked completed: {date}")


# ──────────────────────────────────────────────────────────────────
# Prompt extraction
# ──────────────────────────────────────────────────────────────────

def extract_prompt(section_fragment: str) -> str:
    """
    Extract the prompt text from phase6-supplemental-sequences.md
    for the section whose header contains section_fragment.
    Returns the full section content (header through next ---).
    """
    text = SEQUENCES_FILE.read_text(encoding="utf-8")

    # Find the section header
    header_pattern = rf"###.*{re.escape(section_fragment)}.*"
    header_match = re.search(header_pattern, text)
    if not header_match:
        raise ValueError(
            f"Section '{section_fragment}' not found in {SEQUENCES_FILE.name}.\n"
            f"Check that the header in the sequences file matches exactly."
        )

    start = header_match.start()

    # Find the end: next "---\n\n###" separator or "## WAVE" or EOF
    end_pattern = r"\n---\n"
    end_match = re.search(end_pattern, text[start:])
    if end_match:
        end = start + end_match.start()
    else:
        end = len(text)

    return text[start:end].strip()


def build_gemini_prompt(task_id: str, fix_id: str, raw_prompt: str) -> str:
    """
    Wrap the raw extracted prompt with runner-specific instructions
    that tell gemini where the project root is and what to do after.
    """
    return f"""You are an autonomous remediation agent for TriMCP Phase 6.
Apply @uncle-bob-craft to all changes.

Project root: {PROJECT_ROOT}
All file paths in the instructions below are relative to this root.

━━━ TASK {task_id} · {fix_id} ━━━

{raw_prompt}

━━━ AFTER THE FIX ━━━

When you have completed the fix and the grep verification passes:
1. In the file `to-do-v1-phase6.md`, find the YAML block with `id: {fix_id}`.
2. Set:
     dispatched: yes
     dispatched_by: {task_id}
     completed: 2026-05-12
3. Output exactly on the last line:
   TASK_DONE: {task_id} {fix_id}
"""


# ──────────────────────────────────────────────────────────────────
# Wave sync
# ──────────────────────────────────────────────────────────────────

def wave1_complete() -> bool:
    """Return True if all Wave 1 dependencies are completed in the todo."""
    return all(is_fix_completed(fid) for fid in WAVE1_DEPENDENCIES)


def wait_for_wave1(skip_sync: bool = False, poll_seconds: int = 30) -> None:
    """Block until Wave 1 is complete. Polls the todo file."""
    if skip_sync:
        print("[SYNC] --skip-sync flag set. Bypassing Wave 1 check.")
        return

    missing = [fid for fid in WAVE1_DEPENDENCIES if not is_fix_completed(fid)]
    if not missing:
        print("[SYNC] Wave 1 complete. Proceeding.")
        return

    print(f"[SYNC] Waiting for Wave 1 completion.")
    print(f"       Missing: {', '.join(missing)}")
    print(f"       Checking every {poll_seconds}s. Press Ctrl+C to abort.")
    print()

    while True:
        time.sleep(poll_seconds)
        missing = [fid for fid in WAVE1_DEPENDENCIES if not is_fix_completed(fid)]
        if not missing:
            print("[SYNC] Wave 1 complete. Proceeding.")
            return
        print(f"[SYNC] Still waiting for: {', '.join(missing)}")


# ──────────────────────────────────────────────────────────────────
# Task executor
# ──────────────────────────────────────────────────────────────────

def run_task(task_id: str, fix_id: str, section_fragment: str,
             description: str, dry_run: bool = False) -> bool:
    """
    Execute one task. Returns True on success.
    """
    print()
    print("-"*60)
    print(f"  {task_id}  {fix_id}  {description}")
    print("-"*60)

    # Skip check
    if is_fix_completed(fix_id):
        print(f"  [SKIP] {fix_id} already marked completed in todo. Skipping.")
        return True

    # Extract prompt from sequences document
    try:
        raw_prompt = extract_prompt(section_fragment)
    except ValueError as e:
        print(f"  [ERROR] {e}", file=sys.stderr)
        return False

    full_prompt = build_gemini_prompt(task_id, fix_id, raw_prompt)

    if dry_run:
        print(f"  [DRY-RUN] Would call: gemini -p <prompt> -y")
        print(f"  Prompt preview (first 300 chars):")
        print(f"  {full_prompt[:300]}...")
        return True

    # Call gemini CLI
    print(f"  [RUN] Calling: gemini -p ... -y --model {GEMINI_MODEL}")
    print(f"        (task output follows)")
    print()

    try:
        result = subprocess.run(
            ["gemini", "-p", full_prompt, "-y", "--model", GEMINI_MODEL],
            cwd=str(PROJECT_ROOT),
            check=False,           # we check returncode manually
            timeout=600,           # 10 min max per task
        )
    except subprocess.TimeoutExpired:
        print(f"\n  [ERROR] gemini timed out after 10 minutes for {task_id}.", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(
            "  [ERROR] `gemini` not found in PATH. "
            "Install with: npm install -g @google/gemini-cli",
            file=sys.stderr,
        )
        sys.exit(1)

    if result.returncode != 0:
        print(f"\n  [WARN] gemini exited with code {result.returncode} for {task_id}.")
        print("         Checking if todo was updated anyway...")

    # Confirm completion by checking the todo file
    # (gemini should have updated it as part of the prompt instructions)
    if is_fix_completed(fix_id):
        print(f"\n  [OK] {fix_id} confirmed completed in todo.")
        return True
    else:
        # Gemini may not have updated the file itself; update it here
        print(
            f"  [WARN] {fix_id} not marked in todo by gemini. "
            f"Marking it now (assume success if gemini exit=0)."
        )
        if result.returncode == 0:
            mark_fix_completed(fix_id, task_id)
            return True
        else:
            print(f"  [ERROR] {task_id} ({fix_id}) may have failed. Review gemini output above.")
            return False


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gemini Pro Phase 6 runner — executes tasks W2-C, W3-A, W3-F, W4-E"
    )
    parser.add_argument("--dry-run",    action="store_true", help="Print prompts, do not call gemini")
    parser.add_argument("--skip-sync",  action="store_true", help="Skip Wave 1 completion check")
    parser.add_argument("--task",       metavar="TASK_ID",   help="Run a single task (e.g. W2-C)")
    args = parser.parse_args()

    print()
    print("="*60)
    print("  TriMCP Phase 6 — Gemini Pro Runner")
    print("  Uncle Bob Craft + Antigravity Workflows")
    print(f"  Project root: {PROJECT_ROOT}")
    print("="*60)

    # Validate files exist
    for f in (TODO_FILE, SEQUENCES_FILE):
        if not f.exists():
            print(f"[ERROR] Required file not found: {f}", file=sys.stderr)
            return 1

    # Filter tasks if --task is specified
    tasks = TASKS
    if args.task:
        tasks = [(tid, fid, sec, desc) for tid, fid, sec, desc in TASKS if tid == args.task]
        if not tasks:
            print(f"[ERROR] Unknown task: {args.task}. Valid: {[t[0] for t in TASKS]}", file=sys.stderr)
            return 1

    # Wait for Wave 1
    wait_for_wave1(skip_sync=args.skip_sync)

    # Execute tasks
    failed: list[str] = []
    for task_id, fix_id, section, description in tasks:
        success = run_task(
            task_id=task_id,
            fix_id=fix_id,
            section_fragment=section,
            description=description,
            dry_run=args.dry_run,
        )
        if not success:
            failed.append(f"{task_id} ({fix_id})")

    # Summary
    print()
    print("="*60)
    completed = [t[0] for t in tasks if t[0] not in [f.split()[0] for f in failed]]
    print(f"  Completed: {', '.join(completed) if completed else 'none'}")
    if failed:
        print(f"  Failed:    {', '.join(failed)}")
        print("  Review gemini output above for failed tasks.")
        print("="*60)
        return 1

    print()
    print("  PHASE6-COMPLETE: Gemini Pro runner finished all assigned tasks.")
    print(f"  Tasks completed: FIX-027, FIX-030, FIX-040, FIX-057")
    print("="*60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
