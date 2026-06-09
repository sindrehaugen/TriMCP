#!/usr/bin/env python3
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PROMPTS_FILE = ROOT / "_internal" / "work-docs" / "sessions" / "session_prompts.md"

PREFIX = """1. **One batch = one branch = one commit.** Branch name `batch-NN-shortname`. Never combine batches.
2. **Verify before you act.** Open each target file and confirm the cited symbol/line exists. If it does not match, **STOP and report the discrepancy** — do not invent a fix or create a new file.
3. **Modify only the files listed in the batch.** No new modules, classes, dependencies, or abstractions unless the batch explicitly says so. If you think you need one, STOP and report.
4. **Minimal diff.** Reuse existing utilities (`scoped_pg_session`, `unmanaged_pg_connection`, `append_event`, `NotificationDispatcher`, `acquire_cron_lock`, `encrypt_signing_key`/`decrypt_signing_key`, `require_master_key`). Match the surrounding code style.
5. **Acceptance gate (must all pass before you commit):**
   - `make lint` (ruff check + format) clean
   - `make typecheck` (mypy strict on `nce/`) clean
   - the specific test named in the batch passes
   - existing tests you touched still pass
   - if you changed MCP tool counts, update `tests/test_tool_registry.py` exact-count assertions in the SAME batch
6. **Migrations:** new SQL migrations go in `nce/migrations/` with the next free number (current max = `012`). Mirror any schema change into `nce/schema.sql`. Never edit an existing migration.
7. **WORM/RLS invariants (never violate):** all tenant SQL runs inside `scoped_pg_session`; `append_event` runs inside the same transaction as its data write; never `UPDATE`/`DELETE` `event_log`; never put raw content/PII into `event_log.params`.
8. **Secrets:** `NCE_MASTER_KEY` is environment-only — never read it from, or write it to, a database/settings table/endpoint.
9. **If a test needs live databases**, it is `@pytest.mark.integration`; run it with `pytest -m integration` against `make local-up`. Pure-unit batches must not require Docker.
10. **Report format per batch:** what changed (files), the gate output (lint/typecheck/test green), and anything you had to STOP on.

**Skill legend:** skills are from the Antigravity skills catalogue; load the listed skills for the batch before coding. Pick the first as primary.

"""

FINAL_SUFFIX = """

##Final:
1.: When all steps above are finished. Stop
2.: Launch tool: _internal\\tools\\generate_diff.py and change [NO TAG] to [WAITING TAG] for the Batch in RL.md
3.: When generate_diff.py reports [SUCCESS] - run tool: _internal\\tools\\trigger_tag_audit.py --non-interactive

- If any batch's acceptance gate fails and you cannot fix it within the batch's stated scope, **STOP and report** — do not widen scope or start the next batch.
- After each batch: open a PR titled `Batch NN — <name>`, paste the gate output, and wait for review.
"""


def parse_prompts(content: str) -> list:
    blocks = re.split(r"^(?:#+\s*)?Bat?ch\s+", content, flags=re.MULTILINE)
    prompts = []
    for block in blocks:
        if not block.strip():
            continue
        lines = block.splitlines()
        if not lines:
            continue
        header = lines[0]
        body = "\n".join(lines[1:])

        # Parse header: e.g. "1 - Core Security", "1: Core Security", or "1 Core Security"
        match = re.match(r"^(\d+)\s*[-:]?\s*(.+)$", header.strip())
        if match:
            batch_num = int(match.group(1))
            prompt_name = match.group(2).strip()
            prompts.append({"number": batch_num, "name": prompt_name, "body": body.strip()})
    return prompts


def update_ledger_registry(ledger_path: Path, prompts: list) -> bool:
    if not ledger_path.exists():
        print(f"[ERROR] Fant ikke ledger-filen {ledger_path}.")
        return False

    content = ledger_path.read_text(encoding="utf-8")
    content_normalized = content.replace("\r\n", "\n")

    # Locate ## State Registry
    pattern = r"(## State Registry\n)(.*?)(\n*---)"
    match = re.search(pattern, content_normalized, re.DOTALL | re.IGNORECASE)
    if not match:
        print("[ERROR] Kunne ikke lokalisere ## State Registry-seksjonen i RL.md.")
        return False

    header, registry_text, footer = match.groups()
    existing_lines = registry_text.strip().splitlines()

    # Map existing batch numbers to their line content
    existing_batches = {}
    for line in existing_lines:
        m = re.search(r"Batch\s+(\d+)", line, re.IGNORECASE)
        if m:
            existing_batches[int(m.group(1))] = line

    # Rebuild registry list
    new_lines = []
    sorted_prompts = sorted(prompts, key=lambda x: x["number"])
    for p in sorted_prompts:
        num = p["number"]
        name = p["name"]
        if num in existing_batches:
            new_lines.append(existing_batches[num])
        else:
            status = "[LOCKED]"
            new_lines.append(f"* {status} Batch {num} {name} [NO TAG]")

    new_registry_str = "## State Registry\n" + "\n".join(new_lines) + "\n\n"
    updated_content = (
        content_normalized[: match.start()]
        + f"{new_registry_str}---"
        + content_normalized[match.end() :]
    )

    newline = "\r\n" if "\r\n" in content else "\n"
    ledger_path.write_text(updated_content.replace("\n", newline), encoding="utf-8")
    print("[SUCCESS] Oppdatert RL.md State Registry med eventuelle nye batcher.")
    return True


def setup_session() -> bool:
    ledger_path = ROOT / "RL.md"
    if not ledger_path.exists():
        print(f"[ERROR] RL.md finnes ikke på {ledger_path}. Kan ikke oppdatere eksisterende.")
        return False

    # 2. Check prompts file
    if not PROMPTS_FILE.exists():
        print(f"[ERROR] Fant ikke session_prompts.md på {PROMPTS_FILE}.")
        return False

    content = PROMPTS_FILE.read_text(encoding="utf-8")
    prompts = parse_prompts(content)

    if not prompts:
        print(f"[ERROR] Ingen gyldige batch-prompter funnet i {PROMPTS_FILE.name}.")
        return False

    # 3. Create Batch_[X]_prompt.md for each prompt in the same folder as RL.md
    target_dir = ledger_path.parent
    print(f"[SETUP] Oppretter/oppdaterer prompt-filer i {target_dir.relative_to(ROOT)}...")

    for p in prompts:
        num = p["number"]
        body = p["body"]
        prompt_file = target_dir / f"Batch_{num}_prompt.md"

        # Combine body with prefix and final suffix
        full_content = PREFIX + body + FINAL_SUFFIX

        try:
            prompt_file.write_text(full_content, encoding="utf-8")
            print(f" -> Skrevet {prompt_file.name}")
        except OSError as e:
            print(f"[ERROR] Kunne ikke skrive til {prompt_file.name}: {e}")
            return False

    # 4. Update RL.md State Registry
    print("[SETUP] Oppdaterer RL.md med eventuelle nye batcher...")
    if not update_ledger_registry(ledger_path, prompts):
        return False

    print("[SUCCESS] Oppsettet er fullført på eksisterende ledger.")
    return True


if __name__ == "__main__":
    success = setup_session()
    sys.exit(0 if success else 1)
