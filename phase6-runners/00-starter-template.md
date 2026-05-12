# Phase 6 Agent Starter — Template & Pattern Explanation

This document explains the agent loop pattern used by all four runner files.
Read this once. Then use the per-model .md files or the gemini-pro-runner.py.

---

## The agent loop (Uncle Bob: one thing, named clearly)

```
READ   → read both instruction files at startup
CHECK  → for each task: is it already marked completed in the todo?
SKIP   → if yes, move on
EXEC   → if no, execute the prompt from the sequences document
VERIFY → run the grep check from the prompt
UPDATE → write completed: <date> into the todo YAML block
SYNC   → before crossing from Wave 1 → Wave 2+, confirm Wave 1 is done
REPORT → when queue is empty, output PHASE6-COMPLETE
```

Each step maps to a named responsibility. No step does two things.

---

## The two instruction files

### PROMPTS file
`phase6-supplemental-sequences.md`
Contains one section per task, identified by header like `### W2-C · FIX-027`.
Each section is a self-contained prompt: read first, fix, verify, update todo.

### STATE file
`to-do-v1-phase6.md`
YAML blocks, one per FIX item. The agent writes two fields after completing a task:
  dispatched: yes
  dispatched_by: W<n>-<letter>
  completed: <YYYY-MM-DD>

The agent reads these fields to decide whether to skip a task.

---

## Wave sync protocol

Wave 1 tasks must finish before any Wave 2+ task begins.
Wave 1 tasks are: FIX-013 (Haiku W1-A) and FIX-020 (Composer W1-B).

Sync check: search the state file for both blocks, confirm `completed:` exists.

If sync check fails, the agent outputs:
  WAITING: Wave 1 not complete. Missing: FIX-XXX
and stops until the user types `continue` (GUI agents) or the runner retries automatically (CLI script).

---

## Todo update format

After each completed task, find the YAML block with `id: FIX-XXX` and add/update:

```yaml
id: FIX-013
priority: P0
severity: CRITICAL
source: sonnet
confirmed: yes
dispatched: yes
dispatched_by: W1-A
completed: 2026-05-12       ← ADD THIS LINE
file: trimcp/config.py
...
```

Always add `completed:` immediately after `dispatched_by:`.

---

## Skill declarations (embed in every agent)

@uncle-bob-craft applies to every fix:
- SRP: one fix, one reason to change.
- Extract and name helpers before patching.
- No magic numbers — use named constants.
- Boy Scout: leave touched code cleaner than found.
- Verify with grep before marking complete.
