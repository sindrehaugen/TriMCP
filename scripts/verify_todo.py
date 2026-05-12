#!/usr/bin/env python3
"""
verify_todo.py — Stale To-Do Item Detection for TriMCP Phase 3.

Parses ``to-do-v1-phase3.md`` for all tracked items and cross-references
each against the actual source tree and git history.  Detects:

  * "fixed" items whose referenced file/line-pattern is still present
    (false-positive resolution).
  * "not fixed" items whose referenced file/line-pattern is absent
    (stale tracker — already fixed but never checked off).
  * Items whose referenced file no longer exists at all.
  * Items whose referenced line range exceeds the current file length.
  * Items that have matching git commits providing resolution evidence.

Usage:
    python scripts/verify_todo.py                         # full report
    python scripts/verify_todo.py --json                   # machine-readable JSON
    python scripts/verify_todo.py --ci                     # exit code 1 on stale items
    python scripts/verify_todo.py --git                    # include git-log evidence
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows: force UTF-8 stdout so box-drawing characters don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Constants ──────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
TODO_FILE = REPO_ROOT / "to-do-v1-phase3.md"
TRIMCP_DIR = REPO_ROOT / "trimcp"

# Item header: "### 38. f-string logging in BFS hot path — ..."
_ITEM_HEADER_RE = re.compile(r"^###\s+(?P<num>\d+)\.\s+(?P<title>.+)")
# File reference: `[trimcp/orchestrator.py:949–956]`
_FILE_REF_RE = re.compile(r"\[`?(?P<file>[^`:]+\.py)`?(?::(?P<line_range>[^\]]+))?\]")
# Status keywords
_STATUS_FIXED_RE = re.compile(r"(OK\s*(?:fixed|resolved)|OK)")
_STATUS_NOT_FIXED_RE = re.compile(r"(not fixed|NOT FIXED)")
_STATUS_NEW_RE = re.compile(r"NEW finding")
# Priority tag P0–P5
_PRIORITY_RE = re.compile(r"\b(P[0-5])\b")
# Section break between items
_SECTION_BREAK_RE = re.compile(r"^---$")
# Priority-section headers (## P0, ## P1, …)
_PRIORITY_SECTION_RE = re.compile(r"^## (P[0-5])")


# ── Data Models ────────────────────────────────────────────────────────────


@dataclass
class FileReference:
    path: str  # e.g. "trimcp/orchestrator.py"
    line_range: str  # e.g. "949–956" or ""
    resolved_path: Path | None = None


@dataclass
class TodoItem:
    number: int
    title: str
    priority: str = ""
    status: str = "unknown"  # "not fixed", "fixed", "new finding", "unknown"
    file_refs: list[FileReference] = field(default_factory=list)
    body_lines: list[str] = field(default_factory=list)

    def git_search_terms(self) -> list[str]:
        """Extract search terms for git-log --grep from the item title."""
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.]+", self.title)
        stop = {"with", "from", "that", "this", "the", "not", "for", "and", "are"}
        return [w for w in words if len(w) > 3 and w not in stop][:5]


# ── File Resolution ────────────────────────────────────────────────────────

_SEARCH_ROOTS = [
    TRIMCP_DIR,  # trimcp/orchestrator.py
    REPO_ROOT,  # server.py, admin_server.py
    REPO_ROOT / "admin",  # admin/index.html
    REPO_ROOT / "deploy",  # deploy/compose.stack.env
    REPO_ROOT / "tests",  # tests/conftest.py
    REPO_ROOT / "docs",  # docs/architecture.md
    REPO_ROOT / "scripts",  # scripts/render-env.sh
    REPO_ROOT / "trimcp/orchestrators",  # trimcp/orchestrators/cognitive.py
    REPO_ROOT / "trimcp/extractors",  # trimcp/extractors/chunking.py
    REPO_ROOT / "trimcp/providers",  # trimcp/providers/base.py
]


def _resolve_file(ref_path: str) -> Path | None:
    """Try to locate a file referenced in the todo item across multiple roots."""
    for root in _SEARCH_ROOTS:
        candidate = root / ref_path
        if candidate.exists():
            return candidate.resolve()
        # Some items reference paths like "trimcp/server.py" when the file
        # is actually at the repo root as "server.py".
        if ref_path.startswith("trimcp/"):
            alt = root / ref_path[len("trimcp/") :]
            if alt.exists():
                return alt.resolve()
    return None


# ── Parser ─────────────────────────────────────────────────────────────────


def parse_todo_file(path: Path) -> list[TodoItem]:
    """Parse the markdown todo file into structured TodoItem objects."""
    items: list[TodoItem] = []
    current: TodoItem | None = None

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    for raw_line in lines:
        line = raw_line.rstrip()

        # ── Detect priority-section header (P0, P1, …) ──
        sm = _PRIORITY_SECTION_RE.match(line)
        if sm and current is not None:
            items.append(current)
            current = None

        # ── Section break — flush current ──
        if _SECTION_BREAK_RE.match(line):
            if current is not None:
                items.append(current)
                current = None
            continue

        # ── Detect new item header ──
        m = _ITEM_HEADER_RE.match(line)
        if m:
            if current is not None:
                items.append(current)
            current = TodoItem(
                number=int(m.group("num")),
                title=m.group("title").strip(),
            )
            pm = _PRIORITY_RE.search(current.title)
            if pm:
                current.priority = pm.group(1)
            if _STATUS_FIXED_RE.search(line):
                current.status = "fixed"
            elif _STATUS_NOT_FIXED_RE.search(line):
                current.status = "not fixed"
            continue

        if current is None:
            continue

        current.body_lines.append(line)

        # ── Extract file references ──
        for fm in _FILE_REF_RE.finditer(line):
            ref = FileReference(
                path=fm.group("file"),
                line_range=fm.group("line_range") or "",
            )
            resolved = _resolve_file(fm.group("file"))
            if resolved is not None:
                ref.resolved_path = resolved
            current.file_refs.append(ref)

        # ── Extract status from body ──
        if current.status == "unknown":
            if _STATUS_FIXED_RE.search(line):
                current.status = "fixed"
            elif _STATUS_NEW_RE.search(line):
                current.status = "new finding"
            elif _STATUS_NOT_FIXED_RE.search(line):
                current.status = "not fixed"

        # ── Extract priority from body ──
        if not current.priority:
            pm = _PRIORITY_RE.search(line)
            if pm:
                current.priority = pm.group(1)

    if current is not None:
        items.append(current)

    return items


# ── Pattern Inference ──────────────────────────────────────────────────────


_KNOWN_PATTERNS: dict[str, str] = {
    "utcnow": "utcnow()",
    "datetime.utcnow": "datetime.utcnow",
    "get_event_loop": "get_event_loop()",
    "asyncio.get_event_loop": "asyncio.get_event_loop",
    "Dict": "from typing import Dict",
    "List": "from typing import List",
    "from typing import Dict": "from typing import Dict",
    "from typing import List": "from typing import List",
    "logger.debug(f": 'logger.debug(f"',
    "log.debug(f": 'log.debug(f"',
    "log.info(f": 'log.info(f"',
    "log.warning(f": 'log.warning(f"',
    "log.error(f": 'log.error(f"',
    "f-string logging": "log.",
    "boost_memory": "boost_memory",
    "forget_memory": "forget_memory",
    "resolve_contradiction": "resolve_contradiction",
    "get_running_loop": "get_running_loop()",
    "_stub_vector": "_stub_vector",
    "namespace_id: str = None": "namespace_id: str = None",
    "TRIMCP_PROMETHEUS_PORT": "TRIMCP_PROMETHEUS_PORT",
    "start_http_server": "start_http_server",
    "inconsistent status vocabulary": 'return "passed"',  # old return vocab before fix
    "commit_migration": "commit_migration",
    "pg_try_advisory_lock": "pg_try_advisory_lock",
    "advisory_lock": "pg_try_advisory_lock",
    "asyncio.Lock": "asyncio.Lock",
    "_key_cache_lock": "_key_cache_lock",
    "asynccontextmanager": "asynccontextmanager",
    "scoped_session": "scoped_session",
    "set_namespace_context": "set_namespace_context",
    "_apply_rollback_on_failure": "_apply_rollback_on_failure",
    "store_memory_rolled_back": "store_memory_rolled_back",
    "TRIMCP_DISABLE_MIGRATION_MCP": "TRIMCP_DISABLE_MIGRATION_MCP",
    "_check_admin": "_check_admin",
    "require_scope": "require_scope",
    "memory_salience": "memory_salience",
    "reinforce": "reinforce",
    "_validate_agent_id": "_validate_agent_id",
    "garbage_collector": "gc_orphan_cutoff",
    "GraphRAGTraverser": "GraphRAGTraverser",
    "GRAPH_MAX_CONCURRENT_SEARCHES": "GRAPH_MAX_CONCURRENT_SEARCHES",
    "asyncio.gather": "asyncio.gather(",
    "re_embedder": "re_embedder",
    "MCP_CACHE_TTL": "MCP_CACHE_TTL",
    "generation_counter": "generation_counter",
    "batch deletion": "DELETE.*LIMIT",
    "circuit_breaker": "circuit_breaker",
    "CircuitBreaker": "CircuitBreaker",
    "NLIUnavailableError": "return 0.0",
    "_sync_nli_predict": "_sync_nli_predict",
    "NLI model not loaded": "return 0.0",
    "filterwarnings": "filterwarnings",
    "asyncio_mode": "asyncio_mode",
    "consolidation": "consolidation",
    "ConsolidationOrchestrator": "ConsolidationOrchestrator",
    "mongo_ref_ids": "mongo_ref_ids",
    "_clean_orphaned_cascade": "_clean_orphaned_cascade",
    "consume_resources": "consume_resources",
    "QuotaReservation": "QuotaReservation",
    "FrozenForkConfig": "FrozenForkConfig",
    "ReplayConfigOverrides": "ReplayConfigOverrides",
    "PIIEntity": "PIIEntity",
    "clear_raw_value": "clear_raw_value",
    "NonceStore": "NonceStore",
    "HMACAuthMiddleware": "HMACAuthMiddleware",
    "namespace_isolation_policy": "namespace_isolation_policy",
    "validate_agent_id": "validate_agent_id",
    "scoped_pg_session": "scoped_pg_session",
    "consolidation_run": "consolidation_run",
    "delete_snapshot": "delete_snapshot",
    "parent_event_id": "parent_event_id",
    "check_health": "check_health",
    "check_health_v1": "check_health_v1",
    "as_of_query": "as_of_query",
    "list_contradictions": "list_contradictions",
    "semantic_search": "semantic_search",
    "GetRecentContextRequest": "GetRecentContextRequest",
    "EventType": "EventType",
    "SagaFailureContext": "SagaFailureContext",
    "SagaState.DEFERRED": "SagaState.DEFERRED",
    "audited_session": "audited_session",
    "deleted_at": "deleted_at",
    "ingested_at": "ingested_at",
}


def _infer_search_pattern(item: TodoItem) -> str | None:
    """
    Infer a textual search pattern for an item based on its title and body.

    Strategy (applied in order):
      1. Known-pattern dictionary match on title or body.
      2. Code snippets from the *problem description* (before Fix:/Resolution:).
      3. Short inline code references (backtick-quoted identifiers).
      4. Most distinctive identifier from the title.
    """
    body_text = "\n".join(item.body_lines)

    # ── Strategy 1: Known pattern match ──
    for keyword, pattern in _KNOWN_PATTERNS.items():
        if keyword in body_text or keyword in item.title:
            return pattern

    # ── Strategy 2: Problem-description code snippets (skip Fix: blocks) ──
    pre_fix = body_text.split("**Fix:**")[0]
    pre_fix = pre_fix.split("**Resolution:**")[0]

    code_blocks = re.findall(r"```(?:python)?\n(.*?)```", pre_fix, re.DOTALL)
    if code_blocks:
        longest = max(code_blocks, key=len)
        for candidate_line in longest.split("\n"):
            stripped = candidate_line.strip()
            if len(stripped) > 20 and not stripped.startswith("#"):
                return stripped.strip()

    inline_refs = re.findall(r"`([a-zA-Z_]\w*(?:\(.*?\))?)`", pre_fix)
    if inline_refs:
        return max(set(inline_refs), key=len)

    # ── Strategy 3: Title-derived ──
    title_identifiers = re.findall(
        r"`?([a-zA-Z_][a-zA-Z0-9_.]*(?:\(\))?)`?", item.title
    )
    if title_identifiers:
        stop = {"with", "from", "that", "this", "the", "not", "for", "and", "are", "in"}
        candidates = [w for w in title_identifiers if w.lower() not in stop]
        if candidates:
            return max(candidates, key=len)

    return None


def _pattern_exists(path: Path, pattern: str) -> bool:
    """Check if a textual pattern exists in a file (O(n) substring search)."""
    if not path or not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return pattern in text
    except Exception:
        return False


# ── Verifier ───────────────────────────────────────────────────────────────


@dataclass
class VerificationResult:
    item_number: int
    title: str
    priority: str
    declared_status: str
    file_exists: bool = True
    lines_exist: bool = True
    pattern_still_present: bool | None = None
    git_evidence: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    stale: bool = False


def verify_item(item: TodoItem, with_git: bool = False) -> VerificationResult:
    """Cross-reference a single TodoItem against the source tree."""
    result = VerificationResult(
        item_number=item.number,
        title=item.title,
        priority=item.priority,
        declared_status=item.status,
    )

    # ── File existence and line-range checks ──
    for ref in item.file_refs:
        if ref.resolved_path is None:
            result.file_exists = False
            result.issues.append(f"File not found: {ref.path}")
            continue

        if ref.line_range:
            try:
                parts = ref.line_range.replace("–", "-").split("-")
                start_line = int(parts[0]) if parts[0] else 0
                end_line = int(parts[1]) if len(parts) > 1 and parts[1] else start_line
            except (ValueError, IndexError):
                start_line, end_line = 0, 0

            if start_line > 0:
                file_line_count = _count_lines(ref.resolved_path)
                if end_line > file_line_count:
                    result.lines_exist = False
                    result.issues.append(
                        f"Line range {ref.line_range} exceeds file "
                        f"{ref.path} ({file_line_count} lines)"
                    )

    # ── Pattern verification ──
    pattern = _infer_search_pattern(item)
    if pattern:
        checked_any = False
        found_any = False
        for ref in item.file_refs:
            if ref.resolved_path is None:
                continue
            checked_any = True
            if _pattern_exists(ref.resolved_path, pattern):
                found_any = True
                break

        if checked_any:
            result.pattern_still_present = found_any

            if item.status == "not fixed" and not found_any:
                result.issues.append(
                    f"Declared 'not fixed' but pattern {pattern!r} not found "
                    f"in referenced files — may already be resolved"
                )
            elif item.status == "fixed" and found_any:
                result.issues.append(
                    f"Declared 'fixed' but pattern {pattern!r} still found "
                    f"in referenced files — fix may be incomplete"
                )

    # ── Git evidence (optional, slower) ──
    if with_git:
        result.git_evidence = _check_git_log(item)

    # ── Determine staleness ──
    if result.declared_status == "not fixed" and result.pattern_still_present is False:
        result.stale = True
    elif result.declared_status == "fixed" and result.pattern_still_present is True:
        result.stale = True

    return result


def _count_lines(path: Path) -> int:
    """Return number of lines in a file."""
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _check_git_log(item: TodoItem, max_commits: int = 5) -> list[str]:
    """Search git log for commits touching referenced files or title keywords."""
    evidence: list[str] = []
    try:
        for ref in item.file_refs:
            if ref.resolved_path and ref.resolved_path.exists():
                rel = ref.resolved_path.relative_to(REPO_ROOT)
                result = subprocess.run(
                    ["git", "log", "--oneline", f"-{max_commits}", "--", str(rel)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=REPO_ROOT,
                )
                if result.stdout.strip():
                    evidence.append(f"  {rel}: {result.stdout.strip()}")

        search_terms = item.git_search_terms()
        if search_terms:
            query = "|".join(search_terms)
            result = subprocess.run(
                ["git", "log", "--oneline", f"-{max_commits}", "--grep", query],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=REPO_ROOT,
            )
            if result.stdout.strip():
                evidence.append(f"  title-match: {result.stdout.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        evidence.append("  (git not available or timeout)")
    except ValueError:
        pass
    return evidence


# ── Reporter ───────────────────────────────────────────────────────────────


def generate_report(
    results: list[VerificationResult], json_output: bool = False
) -> str:
    """Generate a human-readable or JSON report."""
    if json_output:
        return json.dumps(
            [
                {
                    "item_number": r.item_number,
                    "title": r.title,
                    "priority": r.priority,
                    "declared_status": r.declared_status,
                    "file_exists": r.file_exists,
                    "lines_exist": r.lines_exist,
                    "pattern_still_present": r.pattern_still_present,
                    "git_evidence": r.git_evidence,
                    "issues": r.issues,
                    "stale": r.stale,
                }
                for r in results
            ],
            indent=2,
            default=str,
        )

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("  TriMCP To-Do Verification Report")
    lines.append(f"  Source: {TODO_FILE.name}")
    lines.append("=" * 72)
    lines.append("")

    stale_count = 0
    fixed_ok = 0
    open_ok = 0
    unresolved = 0
    file_issues = 0

    for r in sorted(results, key=lambda x: x.item_number):
        status_tag = {
            "fixed": "OK",
            "not fixed": "○",
            "new finding": "★",
            "unknown": "?",
        }.get(r.declared_status, "?")

        priority_tag = f"[{r.priority}]" if r.priority else ""
        stale_mark = " ⚠ STALE" if r.stale else ""
        lines.append(
            f"{status_tag} {priority_tag} #{r.item_number}: {r.title}{stale_mark}"
        )

        if r.file_exists is False:
            file_issues += 1
        if r.lines_exist is False:
            file_issues += 1

        if r.issues:
            for issue in r.issues:
                lines.append(f"    └─ {issue}")

        if r.git_evidence:
            for ev in r.git_evidence:
                lines.append(f"    git: {ev[:80]}")

        if r.stale:
            stale_count += 1
        if r.declared_status == "fixed":
            fixed_ok += 1
        elif r.declared_status == "not fixed":
            open_ok += 1
        elif r.declared_status == "new finding":
            unresolved += 1
        elif r.declared_status == "unknown":
            unresolved += 1

        lines.append("")

    # ── Summary ──
    lines.append("-" * 72)
    total = len(results)
    new_findings = sum(1 for r in results if r.declared_status == "new finding")
    unknown = sum(1 for r in results if r.declared_status == "unknown")
    lines.append(f"  Total items:          {total}")
    lines.append(f"  [OK] Fixed (verified):   {fixed_ok}")
    lines.append(f"  ○ Open (verified):    {open_ok}")
    lines.append(f"  ★ New findings:       {new_findings}")
    lines.append(f"  ? Unknown status:     {unknown}")
    lines.append(f"  File issues:          {file_issues}")
    lines.append(f"  ⚠ Stale items:       {stale_count}")
    lines.append("")
    if stale_count > 0:
        lines.append(
            "  ⚠  WARNING: Stale items found — tracker and codebase out of sync!"
        )
    else:
        lines.append("  [OK] Tracker and codebase are in sync.")
    lines.append("-" * 72)

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-reference to-do tracker against source tree and git history.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human-friendly report.",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Exit with code 1 if any stale items are detected (CI mode).",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        help="Include git-log evidence in the report (slower).",
    )
    args = parser.parse_args()

    if not TODO_FILE.exists():
        print(f"ERROR: {TODO_FILE} not found. Run from repo root.", file=sys.stderr)
        return 1

    items = parse_todo_file(TODO_FILE)
    if not items:
        print(f"WARNING: No items found in {TODO_FILE}.", file=sys.stderr)
        return 0

    results = [verify_item(item, with_git=args.git) for item in items]

    report = generate_report(results, json_output=args.json)
    try:
        print(report, flush=True)
    except BrokenPipeError:
        pass  # head/cat piping — not an error

    if args.ci:
        stale_count = sum(1 for r in results if r.stale)
        if stale_count > 0:
            print(
                f"\nCI FAILURE: {stale_count} stale item(s) detected.", file=sys.stderr
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
