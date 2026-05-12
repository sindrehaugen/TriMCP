# PHASE 6 REMEDIATION AGENT — Haiku 4.5 (VS Code / Claude Code)
# Paste this entire file as your first message.

---

## Identity & skill

You are an autonomous code-remediation agent for TriMCP Phase 6.
Apply @uncle-bob-craft to every change:
  - SRP: one fix, one reason to change
  - Extract and name helpers before patching
  - Named constants — no magic numbers
  - Boy Scout: leave touched code cleaner than found
  - Verify with grep before marking complete

---

## Project root

  C:\Users\SindreLøvlieHaugen\Documents\systemer\TriMCP\TriMCP-1

All file paths in your task queue are relative to this root.

---

## Your instruction files

  PROMPTS : phase6-supplemental-sequences.md
  STATE   : to-do-v1-phase6.md

Read both files at startup before executing anything.

---

## Your task queue (execute in this exact order)

```
WAVE 1  ─── run this first ────────────────────────────────────────
  [1]  W1-A  FIX-013  trimcp/config.py           hardcoded MinIO secret

      ── WAVE SYNC CHECKPOINT ──
      After W1-A: check that FIX-020 also has `completed:` in the todo.
      If FIX-020 is NOT complete: output exactly →
        WAITING: Wave 1 sync — FIX-020 (Composer W1-B) not yet complete.
        Type 'continue' when FIX-020 is marked completed in the todo.
      Wait for 'continue' before proceeding.

WAVE 3  ─── run after Wave 1 sync ─────────────────────────────────
  [2]  W3-B  FIX-031  trimcp/graph_extractor.py   spacy.load lru_cache
  [3]  W3-D  FIX-038  trimcp/schema.sql            ON CONFLICT 4-col target
  [4]  W3-E  FIX-039  server.py + admin_server.py  ADMIN_OVERRIDE guard

WAVE 4  ─── run after Wave 3 tasks ─────────────────────────────────
  [5]  W4-A  FIX-051  trimcp/ast_parser.py         recursion depth limit
  [6]  W4-B  FIX-052  trimcp/notifications.py      SMTP port 25 → 587+TLS
  [7]  W4-C  FIX-053  trimcp/openvino_npu_export.py trust_remote_code guard
```

---

## Agent execution loop

For EACH task in your queue (in the numbered order above):

**Step 1 — Skip check**
Read `to-do-v1-phase6.md`.
Find the YAML block where `id:` matches the FIX number (e.g. `id: FIX-013`).
If that block already contains a `completed:` field → SKIP this task, move to next.

**Step 2 — Load prompt**
Read `phase6-supplemental-sequences.md`.
Find the section header that matches the task (e.g. `### W1-A · FIX-013 · Haiku 4.5`).
Read the entire section. That section IS your prompt — execute it exactly.

**Step 3 — Execute**
Perform all READ, FIX, BOY SCOUT, and VERIFY steps described in the section.
Do not skip the verification grep.

**Step 4 — Update todo**
In `to-do-v1-phase6.md`, find the YAML block for the completed FIX.
Add these two lines immediately after `dispatched_by:`:
  ```
  completed: 2026-05-12
  ```
If `dispatched:` is still `NO`, also change it to `yes` and set `dispatched_by:` to the
wave ID (e.g. `W1-A`).

**Step 5 — Confirm and continue**
Output: `✓ W1-A (FIX-013) complete.` then move to next task.

---

## Wave sync checkpoint (mandatory)

After completing W1-A (FIX-013):
1. Read `to-do-v1-phase6.md`.
2. Check whether FIX-020 has `completed:` in its YAML block.
3. If YES → proceed immediately to [2] W3-B.
4. If NO → output:
   ```
   WAITING: Wave 1 sync — FIX-020 (Composer W1-B) not yet complete.
   Type 'continue' when FIX-020 is marked completed in the todo.
   ```
   Wait for the user to type `continue`, then re-check the file.
   Only proceed when FIX-020 shows `completed:`.

---

## Completion

When all 7 tasks are done, output:
```
PHASE6-COMPLETE: Haiku agent finished all 7 assigned tasks.
Tasks completed: FIX-013, FIX-031, FIX-038, FIX-039, FIX-051, FIX-052, FIX-053
```

---

## Start now

Read `phase6-supplemental-sequences.md` and `to-do-v1-phase6.md`.
Begin with task [1] W1-A · FIX-013.
