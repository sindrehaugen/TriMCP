#!/usr/bin/env python3
import asyncio
import re
import subprocess
import sys
from pathlib import Path

# Establish codebase root relative to this script
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


LEDGER_PATH = ROOT / "RL.md"


def find_open_batch(ledger_path: Path) -> tuple[str, str] | tuple[None, None]:
    if not ledger_path.exists():
        print(f"[ERROR] Ledger-filen {ledger_path.name} ble ikke funnet.")
        return None, None

    content = ledger_path.read_text(encoding="utf-8")
    registry_match = re.search(
        r"## State Registry\n(.*?)\n*---", content, re.DOTALL | re.IGNORECASE
    )
    if not registry_match:
        return None, None

    # Match lines like: * [OPEN] Batch 1 Core Security [NO TAG]
    match = re.search(
        r"^\s*\*\s*\[OPEN\]\s+Batch\s+([a-zA-Z0-9_-]+)\s+(.*?)(?=\s+\[|$)",
        registry_match.group(1),
        re.MULTILINE | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, None


def set_batch_running(ledger_path: Path, batch_id: str) -> bool:
    if not ledger_path.exists():
        return False

    content = ledger_path.read_text(encoding="utf-8")
    content_normalized = content.replace("\r\n", "\n")
    pattern = r"(## State Registry\n)(.*?)(\n*---)"
    match = re.search(pattern, content_normalized, re.DOTALL | re.IGNORECASE)
    if not match:
        return False

    header, registry_text, footer = match.groups()
    lines = registry_text.splitlines()
    updated = False
    for i, line in enumerate(lines):
        if re.search(rf"\[OPEN\]\s+Batch\s+{re.escape(batch_id)}\b", line, re.IGNORECASE):
            line = re.sub(r"\[OPEN\]", "[RUNNING]", line, flags=re.IGNORECASE)
            lines[i] = line
            updated = True
            break

    if updated:
        new_registry_text = "\n".join(lines)
        new_block = f"{header}{new_registry_text}{footer}"
        updated_content = (
            content_normalized[: match.start()] + new_block + content_normalized[match.end() :]
        )
        newline = "\r\n" if "\r\n" in content else "\n"
        ledger_path.write_text(updated_content.replace("\n", newline), encoding="utf-8")
        return True
    return False


def set_batch_open(ledger_path: Path, batch_id: str) -> bool:
    if not ledger_path.exists():
        return False

    content = ledger_path.read_text(encoding="utf-8")
    content_normalized = content.replace("\r\n", "\n")
    pattern = r"(## State Registry\n)(.*?)(\n*---)"
    match = re.search(pattern, content_normalized, re.DOTALL | re.IGNORECASE)
    if not match:
        return False

    header, registry_text, footer = match.groups()
    lines = registry_text.splitlines()
    updated = False
    for i, line in enumerate(lines):
        if re.search(rf"\[RUNNING\]\s+Batch\s+{re.escape(batch_id)}\b", line, re.IGNORECASE):
            line = re.sub(r"\[RUNNING\]", "[OPEN]", line, flags=re.IGNORECASE)
            lines[i] = line
            updated = True
            break

    if updated:
        new_registry_text = "\n".join(lines)
        new_block = f"{header}{new_registry_text}{footer}"
        updated_content = (
            content_normalized[: match.start()] + new_block + content_normalized[match.end() :]
        )
        newline = "\r\n" if "\r\n" in content else "\n"
        ledger_path.write_text(updated_content.replace("\n", newline), encoding="utf-8")
        return True
    return False


def check_and_transition_running_passed(ledger_path: Path) -> str | None:
    if not ledger_path.exists():
        return None

    content = ledger_path.read_text(encoding="utf-8")
    content_normalized = content.replace("\r\n", "\n")
    pattern = r"(## State Registry\n)(.*?)(\n*---)"
    match = re.search(pattern, content_normalized, re.DOTALL | re.IGNORECASE)
    if not match:
        return None

    header, registry_text, footer = match.groups()
    lines = registry_text.splitlines()
    updated = False
    passed_batch_num = None

    # 1. Update [RUNNING] with [PASSED TAG] to [DONE]
    for i, line in enumerate(lines):
        if re.search(r"\[RUNNING\].*?\[PASSED TAG\]", line, re.IGNORECASE):
            line = re.sub(r"\[RUNNING\]", "[DONE]", line, flags=re.IGNORECASE)
            lines[i] = line
            updated = True
            batch_match = re.search(r"\bBatch\s+(\d+)\b", line, re.IGNORECASE)
            if batch_match:
                passed_batch_num = int(batch_match.group(1))
            break

    # 2. Transition the next batch from [LOCKED] to [OPEN]
    if passed_batch_num is not None:
        next_batch_num = passed_batch_num + 1
        for i, line in enumerate(lines):
            if re.search(rf"\[LOCKED\].*?\bBatch\s+{next_batch_num}\b", line, re.IGNORECASE):
                line = re.sub(r"\[LOCKED\]", "[OPEN]", line, flags=re.IGNORECASE)
                lines[i] = line
                updated = True
                break
    else:
        # Fallback: check if there are any batches currently in [OPEN], [RUNNING], [RUNNING TAG], or [WAITING TAG] status
        active_batch_found = False
        done_batches = []
        for line in lines:
            if re.search(r"\[(?:OPEN|RUNNING|RUNNING TAG|WAITING TAG)\]", line, re.IGNORECASE):
                active_batch_found = True
                break
            if re.search(r"\[DONE\].*?\[PASSED TAG\]", line, re.IGNORECASE):
                batch_match = re.search(r"\bBatch\s+(\d+)\b", line, re.IGNORECASE)
                if batch_match:
                    done_batches.append(int(batch_match.group(1)))

        if not active_batch_found and done_batches:
            max_done = max(done_batches)
            next_batch_num = max_done + 1
            for i, line in enumerate(lines):
                if re.search(rf"\[LOCKED\].*?\bBatch\s+{next_batch_num}\b", line, re.IGNORECASE):
                    line = re.sub(r"\[LOCKED\]", "[OPEN]", line, flags=re.IGNORECASE)
                    lines[i] = line
                    updated = True
                    break

    if updated:
        new_registry_text = "\n".join(lines)
        new_block = f"{header}{new_registry_text}{footer}"
        updated_content = (
            content_normalized[: match.start()] + new_block + content_normalized[match.end() :]
        )
        newline = "\r\n" if "\r\n" in content else "\n"
        ledger_path.write_text(updated_content.replace("\n", newline), encoding="utf-8")
        return str(passed_batch_num) if passed_batch_num is not None else None
    return None


def are_all_batches_finished_passed(ledger_path: Path) -> bool:
    if not ledger_path.exists():
        return False

    content = ledger_path.read_text(encoding="utf-8")
    registry_match = re.search(
        r"## State Registry\n(.*?)\n*---", content, re.DOTALL | re.IGNORECASE
    )
    if not registry_match:
        return False

    registry_text = registry_match.group(1)
    lines = [line.strip() for line in registry_text.splitlines() if line.strip()]
    if not lines:
        return False

    for line in lines:
        if "Batch" in line:
            if not (
                re.search(r"\[DONE\]", line, re.IGNORECASE)
                and re.search(r"\[PASSED TAG\]", line, re.IGNORECASE)
            ):
                return False
    return True


def commit_passed_batch(batch_id: str) -> None:
    """Stage all changes and commit them when a batch reaches [PASSED].

    Skips silently (no error) when the working tree is clean.
    """
    try:
        subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    except Exception as e:
        print(f"[ERROR] 'git add -A' feilet: {e}")
        return

    # `git diff --cached --quiet` exits 0 when nothing is staged, 1 when there are staged changes.
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if staged.returncode == 0:
        print(f"[GIT] Ingen endringer å committe for Batch {batch_id}.")
        return

    try:
        subprocess.run(
            ["git", "commit", "-m", f"Batch {batch_id}: TAG passed"],
            cwd=ROOT,
            check=True,
        )
        print(f"[GIT] Committet endringer for Batch {batch_id} (TAG passed).")
    except Exception as e:
        print(f"[ERROR] 'git commit' feilet: {e}")


async def start_batch_agent() -> bool:
    # 1. Transition any RUNNING batch with PASSED TAG to FINISHED and PASSED TAG
    passed_batch_id = check_and_transition_running_passed(LEDGER_PATH)
    if passed_batch_id:
        print(f"[ORCHESTRATOR] Batch {passed_batch_id} har status [PASSED]. Committer arbeid...")
        commit_passed_batch(passed_batch_id)

    # 2. If all batches are FINISHED and PASSED TAG, run archive_gate.py
    if are_all_batches_finished_passed(LEDGER_PATH):
        print("[START RL] Alle batcher er fullført og godkjent (PASSED TAG). Starter arkivering...")
        archive_script = ROOT / "_internal" / "tools" / "archive_gate.py"
        try:
            subprocess.run([sys.executable, str(archive_script)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Feilet under kjøring av archive_gate.py: {e}")
            return False
        return True

    # 3. Otherwise find the next [OPEN] batch
    batch_id, batch_name = find_open_batch(LEDGER_PATH)
    if not batch_id:
        print("[INFO] Ingen batcher med status [OPEN] funnet i RL.md.")
        return False

    prompt_file = ROOT / f"Batch_{batch_id}_prompt.md"
    if not prompt_file.exists():
        print(f"[ERROR] Fant ikke prompt-filen {prompt_file.name} i rotmappen.")
        return False

    print(f"[START RL] Fant [OPEN] Batch {batch_id}: {batch_name}")

    print("[START RL] Oppdaterer status til [RUNNING] i RL.md...")
    if not set_batch_running(LEDGER_PATH, batch_id):
        print("[ERROR] Kunne ikke oppdatere batch-status til [RUNNING] i RL.md.")
        return False

    prompt_content = prompt_file.read_text(encoding="utf-8")

    # Copy prompt to clipboard and trigger Ctrl+Shift+L in Antigravity IDE
    print(f"[START RL] Kopierer prompt fra {prompt_file.name} til utklippstavlen...")
    try:
        subprocess.run("clip", input=prompt_content, text=True, encoding="utf-8", check=True)
    except Exception as e:
        print(f"[ERROR] Kunne ikke kopiere til utklippstavlen: {e}")
        print("[START RL] Tilbakestiller batch-status til [OPEN] i RL.md...")
        set_batch_open(LEDGER_PATH, batch_id)
        return False

    non_interactive = (
        "--non-interactive" in sys.argv or "--automated" in sys.argv or not sys.stdin.isatty()
    )
    if not non_interactive:
        print(
            "[WARNING] The script is about to simulate keyboard shortcuts (Ctrl+Shift+L) in Cursor."
        )
        try:
            user_input = input(
                "Please type 'ok' and press ENTER to authorize and send keystrokes, or any other key to copy to clipboard only: "
            )
            if user_input.strip().lower() != "ok":
                print(
                    "[INFO] Keystroke simulation skipped. Prompt has been copied to clipboard; paste it manually."
                )
                set_batch_open(LEDGER_PATH, batch_id)
                return False
        except KeyboardInterrupt:
            print(
                "\n[INFO] Cancelled by user. Prompt has been copied to clipboard; paste it manually."
            )
            set_batch_open(LEDGER_PATH, batch_id)
            return False

    print("[START RL] Sender Ctrl+Shift+L for å åpne ny chat i Antigravity IDE...")
    try:
        ps_command = """
        $wshell = New-Object -ComObject Wscript.Shell;
        $wshell.SendKeys("^+l")
        Start-Sleep -Milliseconds 800
        $wshell.SendKeys("^v")
        Start-Sleep -Milliseconds 500
        $wshell.SendKeys("{ENTER}")
        """
        subprocess.run(["powershell", "-Command", ps_command], check=True)
    except Exception as e:
        print(f"[ERROR] Feilet under simulering av tastetrykk: {e}")
        print("[INFO] Vennligst trykk Ctrl+Shift+L manuelt og lim inn prompten.")

    print(f"[SUCCESS] Batch {batch_id} fullført.")
    return True


if __name__ == "__main__":
    success = asyncio.run(start_batch_agent())
    sys.exit(0 if success else 1)
