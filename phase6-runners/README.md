# Phase 6 Runner System
# TriMCP Supplemental Remediation — Agent Execution Scripts

## Architecture

```
phase6-supplemental-sequences.md   ← prompt library (read by all agents)
to-do-v1-phase6.md                 ← shared state file (written by all agents)
phase6-runners/
├── README.md                      ← this file
├── 00-starter-template.md         ← explains the agent loop pattern
├── haiku-agent.md                 ← paste into VS Code / Claude Code (Haiku 4.5)
├── composer-agent.md              ← paste into Cursor Composer 2
├── flash-agent.md                 ← paste into Google Antigravity (Gemini Flash)
├── gemini-pro-runner.py           ← run from terminal: python gemini-pro-runner.py
└── wave-sync.py                   ← utility: check wave completion status
```

## How to run

### Step 1 — Start Wave 1 (both in parallel)

Open two sessions simultaneously:
- Paste `haiku-agent.md` into VS Code Claude Code → it will execute W1-A (FIX-013)
- Paste `composer-agent.md` into Cursor Composer → it will execute W1-B (FIX-020)

Both agents will stop after their Wave 1 task and output "WAITING: Wave 1 sync — waiting for partner."

### Step 2 — Confirm Wave 1 complete

Run from terminal:
  python phase6-runners/wave-sync.py

This reads to-do-v1-phase6.md and prints the completion status of FIX-013 and FIX-020.

When both show `completed:`, proceed.

### Step 3 — Unblock agents (Waves 2–4, all in parallel)

In the same sessions that ran Wave 1 (they are still open and waiting):
- Type `continue` in the Haiku VS Code session
- Type `continue` in the Cursor Composer session
- Open a terminal and run: `python phase6-runners/gemini-pro-runner.py`
- Paste `flash-agent.md` into Google Antigravity

All agents now run their remaining tasks in parallel.
Gemini Pro executes W2-C → W3-A → W3-F → W4-E sequentially (script handles this).
The three GUI agents (Haiku, Composer, Flash) execute their queues autonomously.

### Step 4 — Final verification

Run:
  python phase6-runners/wave-sync.py --all

This prints completion status for all 19 FIX items.

## Wave ownership

| Task  | FIX   | Wave | Tool         |
|-------|-------|------|--------------|
| W1-A  | 013   | 1    | Haiku        |
| W1-B  | 020   | 1    | Composer     |
| W2-A  | 025   | 2    | Composer     |
| W2-B  | 026   | 2    | Composer     |
| W2-C  | 027   | 2    | Gemini Pro   |
| W2-D  | 029   | 2    | Composer     |
| W3-A  | 030   | 3    | Gemini Pro   |
| W3-B  | 031   | 3    | Haiku        |
| W3-C  | 032   | 3    | Composer     |
| W3-D  | 038   | 3    | Haiku        |
| W3-E  | 039   | 3    | Haiku        |
| W3-F  | 040   | 3    | Gemini Pro   |
| W3-G  | 041   | 3    | Composer     |
| W4-A  | 051   | 4    | Haiku        |
| W4-B  | 052   | 4    | Haiku        |
| W4-C  | 053   | 4    | Haiku        |
| W4-D  | 054+055 | 4  | Flash        |
| W4-E  | 057   | 4    | Gemini Pro   |
| W4-F  | 046   | 4    | Composer     |

## Wave sync rule
Wave 1 (FIX-013 + FIX-020) must be marked `completed:` in the todo
before any agent proceeds past Wave 1.
