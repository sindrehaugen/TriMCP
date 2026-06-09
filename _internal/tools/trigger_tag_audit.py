#!/usr/bin/env python3
import re
import sys
from pathlib import Path
import subprocess

# Script is at BASE/_internal/tools/ — root is two levels up
ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "RL.md"
TAG_TEMPLATE = ROOT / "_internal" / "templates" / "tag_audit.md"


def find_running_batch_id(content: str) -> str | None:
    registry_match = re.search(r"## State Registry\n(.*?)\n*---", content, re.DOTALL | re.IGNORECASE)
    if not registry_match:
        return None
    match = re.search(r"\[RUNNING\]\s+Batch\s+([a-zA-Z0-9_-]+)", registry_match.group(1), re.IGNORECASE)
    return match.group(1) if match else None


def find_passed_batch_id(content: str) -> str | None:
    """Return the id of the first batch whose TAG audit has reached [PASSED] / [PASSED TAG]."""
    registry_match = re.search(r"## State Registry\n(.*?)\n*---", content, re.DOTALL | re.IGNORECASE)
    if not registry_match:
        return None
    for line in registry_match.group(1).splitlines():
        if re.search(r"\[PASSED(?:\s+TAG)?\]", line, re.IGNORECASE):
            batch_match = re.search(r"\bBatch\s+([a-zA-Z0-9_-]+)\b", line, re.IGNORECASE)
            if batch_match:
                return batch_match.group(1)
    return None


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


def update_tag_status(ledger_path: Path, batch_id: str, old_status_pattern: str, new_status: str) -> bool:
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
        if re.search(rf"\bBatch\s+{re.escape(batch_id)}\b", line, re.IGNORECASE):
            new_line, count = re.subn(old_status_pattern, new_status, line, flags=re.IGNORECASE)
            if count > 0:
                lines[i] = new_line
                updated = True
                break
    if updated:
        new_registry_text = "\n".join(lines)
        new_block = f"{header}{new_registry_text}{footer}"
        updated_content = content_normalized[:match.start()] + new_block + content_normalized[match.end():]
        newline = "\r\n" if "\r\n" in content else "\n"
        ledger_path.write_text(updated_content.replace("\n", newline), encoding="utf-8")
        return True
    return False


def trigger_tag_protocol() -> bool:
    for path in (LEDGER_PATH, TAG_TEMPLATE):
        if not path.exists():
            print(f"[ERROR] Fant ikke {path.relative_to(ROOT)}. Avbryter.")
            sys.exit(1)

    content = LEDGER_PATH.read_text(encoding="utf-8")

    # If a batch has already reached [PASSED], commit its work before triggering anything else.
    passed_batch_id = find_passed_batch_id(content)
    if passed_batch_id:
        print(f"[ORCHESTRATOR] Batch {passed_batch_id} har status [PASSED]. Committer arbeid før triggering...")
        commit_passed_batch(passed_batch_id)

    batch_id = find_running_batch_id(content)

    if not batch_id:
        print("[ERROR] Ingen batch med status [RUNNING] funnet i RL.md.")
        sys.exit(1)

    diff_file = ROOT / f"diff_batch_{batch_id}.md"
    if not diff_file.exists():
        print(f"[ERROR] {diff_file.name} ikke funnet på disk. Avbryter.")
        sys.exit(1)

    # 1. Update tag status in RL.md to [RUNNING TAG]
    print(f"[ORCHESTRATOR] Oppdaterer status for Batch {batch_id} til [RUNNING TAG]...")
    if not update_tag_status(LEDGER_PATH, batch_id, r"\[Waiting TAG\]", "[RUNNING TAG]"):
        print(f"[WARNING] Kunne ikke oppdatere status fra [Waiting TAG] til [RUNNING TAG].")

    print(f"[ORCHESTRATOR] Batch {batch_id} klar. Starter TAG-sesjon...")

    prompt = (
        TAG_TEMPLATE.read_text(encoding="utf-8")
        + "\n\n---\n\n"
        + diff_file.read_text(encoding="utf-8")
    )

    # 2. Copy prompt to clipboard
    try:
        subprocess.run("clip", input=prompt, text=True, encoding="utf-8", check=True)
    except Exception as e:
        print(f"[ERROR] Kunne ikke kopiere til utklippstavlen: {e}")
        return False

    print("[WARNING] The script is about to simulate keyboard shortcuts (Ctrl+Shift+L) in Cursor.")
    try:
        user_input = input("Please type 'ok' and press ENTER to authorize and send keystrokes, or any other key to copy to clipboard only: ")
        if user_input.strip().lower() != "ok":
            print("[INFO] Keystroke simulation skipped. Prompt has been copied to clipboard; paste it manually.")
            return False
    except KeyboardInterrupt:
        print("\n[INFO] Cancelled by user. Prompt has been copied to clipboard; paste it manually.")
        return False

    print(f"[ORCHESTRATOR] Sender Ctrl+Shift+L for å åpne ny chat i Antigravity IDE...")
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

    print(f"[SUCCESS] TAG-protokoll startet for Batch {batch_id}.")
    return True


if __name__ == "__main__":
    trigger_tag_protocol()