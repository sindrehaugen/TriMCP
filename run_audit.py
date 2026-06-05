import os
import ast
import tokenize
import re
from io import BytesIO
from collections import defaultdict
import hashlib
import json

EXCLUDED_DIRS = {'.git', '.github', '_internal', 'build', 'node_modules', '__pycache__', '.pytest_cache'}
EXCLUDED_EXTS = {'.pyc', '.pyo', '.lock', '.exe', '.pdf', '.png', '.jpg', '.jpeg', '.vbs', '.sum', '.mod'}
TARGET_EXTS = {'.py', '.go', '.sh', '.html', '.css', '.tf', '.bicep'}

def is_target_file(path):
    if any(ex in path for ex in EXCLUDED_DIRS):
        return False
    ext = os.path.splitext(path)[1]
    if ext not in TARGET_EXTS:
        return False
    return True

issues = defaultdict(list)
files_analyzed = 0
total_anomalies = 0
module_risk = defaultdict(int)

class PythonVisitor(ast.NodeVisitor):
    def __init__(self, filename, lines):
        self.filename = filename
        self.lines = lines
        self.issues = []

    def add_issue(self, line_no, severity, rule_id, description):
        if line_no < 1 or line_no > len(self.lines):
            snippet = "N/A"
        else:
            snippet = self.lines[line_no - 1].strip()
        self.issues.append({
            "line": line_no,
            "severity": severity,
            "rule_id": rule_id,
            "description": description,
            "snippet": snippet
        })

    def visit_FunctionDef(self, node):
        if not node.returns and node.name != "__init__":
            self.add_issue(node.lineno, "Warning", "PY_TYPING", f"Missing return type hint for function '{node.name}'")
        for arg in node.args.args:
            if arg.arg != 'self' and arg.arg != 'cls' and not arg.annotation:
                self.add_issue(node.lineno, "Warning", "PY_TYPING", f"Missing type hint for argument '{arg.arg}' in function '{node.name}'")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if not node.returns and node.name != "__init__":
            self.add_issue(node.lineno, "Warning", "PY_TYPING", f"Missing return type hint for async function '{node.name}'")
        for arg in node.args.args:
            if arg.arg != 'self' and arg.arg != 'cls' and not arg.annotation:
                self.add_issue(node.lineno, "Warning", "PY_TYPING", f"Missing type hint for argument '{arg.arg}' in async function '{node.name}'")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if not node.body:
            self.add_issue(node.lineno, "Error", "PY_EMPTY_EXCEPT", "Empty except block (silenced exception)")
        elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.add_issue(node.lineno, "Error", "PY_EXCEPT_PASS", "Unhandled exception block (except: pass)")
        self.generic_visit(node)

    def visit_Global(self, node):
        self.add_issue(node.lineno, "Warning", "PY_GLOBAL", f"Implicit global declaration: {', '.join(node.names)}")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in ['eval', 'exec']:
                self.add_issue(node.lineno, "Error", "PY_UNSAFE_CALL", f"Unsafe evaluation using '{node.func.id}'")
        self.generic_visit(node)

def analyze_python(path, lines, content):
    try:
        tree = ast.parse(content)
        visitor = PythonVisitor(path, lines)
        visitor.visit(tree)
        return visitor.issues
    except SyntaxError as e:
        snippet = lines[e.lineno - 1].strip() if e.lineno and e.lineno <= len(lines) else ""
        return [{
            "line": e.lineno or 0,
            "severity": "Error",
            "rule_id": "PY_SYNTAX",
            "description": f"Syntax error: {e.msg}",
            "snippet": snippet
        }]

def analyze_go(path, lines):
    issues = []
    # Basic regex heuristics for Go
    for i, line in enumerate(lines):
        line_no = i + 1
        stripped = line.strip()

        # Naked returns in complex functions
        if re.match(r'^return$', stripped):
            # heuristic: check if function might be complex (hard to know perfectly without AST, but flag to be safe or check context)
            pass

        # Check shadowing roughly by re-declaration in inner scopes
        # (Very naive, best we can do with regex)
        if ':=' in stripped and 'err :=' not in stripped:
            pass # hard to be accurate without AST

    # Go unhandled errors roughly: func calling and no check
    content = '\n'.join(lines)
    err_vars = re.findall(r'(\w+)\s*,?\s*err\s*:=', content)

    # Just looking for basic anti-patterns
    for i, line in enumerate(lines):
        line_no = i + 1
        if re.search(r'\bpanic\(', line):
            issues.append({"line": line_no, "severity": "Warning", "rule_id": "GO_PANIC", "description": "Usage of panic", "snippet": line.strip()})

    return issues

def analyze_shell(path, lines):
    issues = []
    has_set_e = False
    has_set_pipefail = False
    for i, line in enumerate(lines):
        line_no = i + 1
        stripped = line.strip()
        if stripped.startswith('set -e') or ' -e ' in stripped:
            has_set_e = True
        if stripped.startswith('set -o pipefail') or ' pipefail' in stripped:
            has_set_pipefail = True

        # Unquoted variables: $var not in quotes
        if re.search(r'(?<!")\$[a-zA-Z_][a-zA-Z0-9_]*(?!")', stripped):
             issues.append({"line": line_no, "severity": "Warning", "rule_id": "SH_UNQUOTED_VAR", "description": "Unquoted variable detected", "snippet": stripped})

    if lines and lines[0].startswith('#!'):
        if not has_set_e:
            issues.append({"line": 1, "severity": "Warning", "rule_id": "SH_NO_SET_E", "description": "Missing set -e initialization", "snippet": lines[0].strip()})
        if not has_set_pipefail:
            issues.append({"line": 1, "severity": "Warning", "rule_id": "SH_NO_PIPEFAIL", "description": "Missing set -o pipefail initialization", "snippet": lines[0].strip()})
    return issues

def analyze_frontend_iac(path, lines):
    issues = []
    # Broken brackets check
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    for i, line in enumerate(lines):
        for char in line:
            if char in '({[':
                stack.append((char, i+1, line.strip()))
            elif char in ')}]':
                if not stack or stack[-1][0] != pairs[char]:
                    issues.append({
                        "line": i+1, "severity": "Error", "rule_id": "STRUCT_BROKEN_BRACKET",
                        "description": f"Unmatched closing bracket '{char}'", "snippet": line.strip()
                    })
                elif stack:
                    stack.pop()
    for char, line_no, snippet in stack:
        issues.append({
            "line": line_no, "severity": "Error", "rule_id": "STRUCT_UNCLOSED_BRACKET",
            "description": f"Unclosed bracket '{char}'", "snippet": snippet
        })
    return issues

# Phase 3: Cross-Module Duplication Scan
duplication_blocks = []
blocks_by_hash = defaultdict(list)

def tokenize_code(content, ext):
    if ext == '.py':
        tokens = []
        try:
            for tok in tokenize.tokenize(BytesIO(content.encode('utf-8')).readline):
                if tok.type in (tokenize.NAME, tokenize.OP, tokenize.NUMBER, tokenize.STRING):
                    tokens.append(tok.string)
        except Exception:
            tokens = re.findall(r'\w+|[^\w\s]', content)
        return tokens
    else:
        return re.findall(r'\w+|[^\w\s]', content)

def extract_blocks(path, lines, ext):
    # sliding window of 6 lines
    for i in range(len(lines) - 5):
        block_lines = lines[i:i+6]
        block_content = '\n'.join(block_lines)
        if not block_content.strip(): continue
        tokens = tokenize_code(block_content, ext)
        if len(tokens) >= 50 or len(block_lines) >= 6:
            # Structurally similar: replace variable names with VAR
            struct_tokens = []
            for t in tokens:
                if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', t) and t not in ['if', 'else', 'for', 'while', 'def', 'class', 'return', 'import', 'from']:
                    struct_tokens.append('VAR')
                else:
                    struct_tokens.append(t)
            h = hashlib.md5(" ".join(struct_tokens).encode('utf-8')).hexdigest()
            blocks_by_hash[h].append((path, i+1, i+6, block_content))

def main():
    global files_analyzed, total_anomalies

    for root, _, files in os.walk('.'):
        if any(ex in root for ex in EXCLUDED_DIRS):
            continue

        for file in files:
            path = os.path.join(root, file)
            path_norm = os.path.normpath(path)

            if not is_target_file(path_norm):
                continue

            files_analyzed += 1
            ext = os.path.splitext(file)[1]
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            lines = content.splitlines()
            if not lines: continue

            file_issues = []
            if ext == '.py':
                file_issues = analyze_python(path_norm, lines, content)
            elif ext == '.go':
                file_issues = analyze_go(path_norm, lines)
            elif ext == '.sh':
                file_issues = analyze_shell(path_norm, lines)
            elif ext in ('.html', '.css', '.tf', '.bicep'):
                file_issues = analyze_frontend_iac(path_norm, lines)

            if file_issues:
                issues[path_norm].extend(file_issues)
                total_anomalies += len(file_issues)
                module_risk[path_norm] += len(file_issues)

            # Duplication phase 2/3
            extract_blocks(path_norm, lines, ext)

    # Filter duplications across different files or non-overlapping
    duplicates = []
    dup_id = 1
    for h, blocks in blocks_by_hash.items():
        if len(blocks) < 2: continue
        # Find unique files in this group
        unique_files = list({b[0] for b in blocks})
        if len(unique_files) >= 2:
            b1 = blocks[0]
            # Find a block from a different file
            b2 = next(b for b in blocks if b[0] != b1[0])
            duplicates.append({
                "id": f"DUP_{dup_id:03d}",
                "match": "100%", # Based on struct token hash
                "file_a": b1[0], "lines_a": (b1[1], b1[2]),
                "file_b": b2[0], "lines_b": (b2[1], b2[2]),
                "code": b1[3]
            })
            dup_id += 1
            # limit max duplicates to report so it doesn't explode
            if dup_id > 100: break

    highest_risk_module = max(module_risk, key=module_risk.get) if module_risk else "None"

    # Write report
    with open("Jules_audit_report.md", "w", encoding='utf-8') as f:
        f.write("# Repository Code Integrity & Duplication Audit Report\n\n")
        f.write("## 1. Executive Analytics Summary\n")
        f.write(f"- **Total Source Files Analyzed:** {files_analyzed}\n")
        f.write(f"- **Total Syntax/Linting Anomalies:** {total_anomalies}\n")
        f.write(f"- **Identified Duplication Redundancies:** {len(duplicates)}\n")
        f.write(f"- **Highest-Risk Module Cluster:** {highest_risk_module}\n\n")

        f.write("## 2. Granular Syntax & Static Analysis Issues\n")
        for path, file_issues in sorted(issues.items()):
            f.write(f"### Module: `{path}`\n")
            f.write("| Line | Severity | Rule ID | Description | Code Snippet Context |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- |\n")
            for iss in file_issues:
                snippet = iss['snippet'].replace('|', '\\|')
                f.write(f"| `{iss['line']:02d}` | {iss['severity']} | {iss['rule_id']} | {iss['description']} | `{snippet}` |\n")
            f.write("\n---\n\n")

        f.write("## 3. Structural Code Duplication Ledger\n")
        for d in duplicates:
            f.write(f"### Redundancy ID: `{d['id']}`\n")
            f.write(f"- **Similarity Metric:** {d['match']} Match\n")
            f.write(f"- **Target Vector A:** `{d['file_a']}` (Lines `{d['lines_a'][0]}`-`{d['lines_a'][1]}`)\n")
            f.write(f"- **Target Vector B:** `{d['file_b']}` (Lines `{d['lines_b'][0]}`-`{d['lines_b'][1]}`)\n")
            f.write("- **Shared Code Block Profile:**\n")
            ext = os.path.splitext(d['file_a'])[1][1:]
            f.write(f"```{ext}\n{d['code']}\n```\n")

            # Suggest remediation
            if "scripts" in d['file_a'] and "scripts" in d['file_b']:
                rem = "Abstract into unified helper script in scripts/"
            elif "nce" in d['file_a'] or "nce" in d['file_b']:
                rem = "Abstract into unified helper module under nce/utils.py"
            else:
                rem = "Extract to a shared common library/module"
            f.write(f"Remediation Vector: {rem}\n\n")

if __name__ == "__main__":
    main()
