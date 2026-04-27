"""
Phase 3.2: AST-Aware Code Parser
Parses source files into function/class chunks using Tree-sitter.
Falls back to a line-based splitter if Tree-sitter bindings are unavailable.
Yields CodeChunk objects consumed by TriStackEngine.index_code_file().
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator

log = logging.getLogger("tri-stack-ast")

SUPPORTED_LANGUAGES = ("python", "javascript", "typescript", "go", "rust")


@dataclass
class CodeChunk:
    node_type: str    # 'function' | 'class' | 'block'
    name: str
    code_string: str
    start_line: int
    end_line: int


# --- Tree-sitter backend (active when packages are installed) ---

def _try_treesitter_parse(raw_code: str, language: str) -> list[CodeChunk] | None:
    """
    Attempt Tree-sitter parse. Returns None if bindings are missing so the
    caller can fall back gracefully — no hard import-time crash.
    """
    try:
        from tree_sitter import Language, Parser
    except ImportError:
        return None

    try:
        if language == "python":
            import tree_sitter_python as ts_lang
            lang = Language(ts_lang.language())
        elif language == "javascript":
            import tree_sitter_javascript as ts_lang
            lang = Language(ts_lang.language())
        elif language == "typescript":
            import tree_sitter_typescript as ts_lang
            lang = Language(ts_lang.language_typescript())
        elif language == "go":
            import tree_sitter_go as ts_lang
            lang = Language(ts_lang.language())
        elif language == "rust":
            import tree_sitter_rust as ts_lang
            lang = Language(ts_lang.language())
        else:
            return None
    except Exception as e:
        log.warning(f"Tree-sitter language binding unavailable for '{language}': {e}")
        return None

    parser = Parser(lang)
    tree = parser.parse(raw_code.encode())

    # Node types that represent meaningful semantic boundaries
    target_types = {
        "python":     {"function_definition", "class_definition"},
        "javascript": {"function_declaration", "function_expression",
                       "arrow_function", "class_declaration", "method_definition"},
        "typescript": {"function_declaration", "generator_function_declaration",
                       "class_declaration", "method_definition", "interface_declaration", "type_alias_declaration"},
        "go":         {"function_declaration", "method_declaration", "type_declaration"},
        "rust":       {"function_item", "struct_item", "enum_item", "impl_item", "trait_item"},
    }
    targets = target_types.get(language, set())
    lines = raw_code.splitlines()
    chunks: list[CodeChunk] = []

    def _extract_name(node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode()
        return "<anonymous>"

    def _walk(node):
        if node.type in targets:
            start = node.start_point[0]   # 0-indexed
            end = node.end_point[0]
            code_string = "\n".join(lines[start : end + 1])
            node_type = "function" if "function" in node.type else "class"
            chunks.append(CodeChunk(
                node_type=node_type,
                name=_extract_name(node),
                code_string=code_string,
                start_line=start + 1,    # 1-indexed for storage
                end_line=end + 1,
            ))
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return chunks if chunks else None


# --- Line-based fallback splitter ---

def _line_splitter_parse(raw_code: str, language: str) -> list[CodeChunk]:
    """
    Heuristic splitter used when Tree-sitter is unavailable.
    Detects top-level def/class (Python) or function/class (JS) by indentation.
    """
    lines = raw_code.splitlines()
    chunks: list[CodeChunk] = []

    if language == "python":
        triggers = ("def ", "class ", "async def ")
    else:
        triggers = ("function ", "class ", "const ", "let ", "var ", "async function ")

    current_start: int | None = None
    current_name = "<block>"
    current_type = "block"

    def _flush(end_line: int):
        if current_start is not None:
            block = "\n".join(lines[current_start - 1 : end_line])
            chunks.append(CodeChunk(
                node_type=current_type,
                name=current_name,
                code_string=block,
                start_line=current_start,
                end_line=end_line,
            ))

    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if any(stripped.startswith(t) for t in triggers) and (
            language == "python" and not line.startswith(" ")
            or language != "python"
        ):
            _flush(i - 1)
            current_start = i
            parts = stripped.split()
            current_name = parts[1].split("(")[0] if len(parts) > 1 else "<anonymous>"
            current_type = "class" if "class" in stripped else "function"

    _flush(len(lines))
    return chunks


# --- Public API ---

def parse_file(raw_code: str, language: str) -> Iterator[CodeChunk]:
    """
    Parse source code into CodeChunk objects.
    Tries Tree-sitter first; falls back to line-based heuristic.
    """
    if language not in SUPPORTED_LANGUAGES:
        log.warning(f"Language '{language}' not supported — yielding single whole-file chunk.")
        yield CodeChunk(
            node_type="file",
            name="<whole_file>",
            code_string=raw_code,
            start_line=1,
            end_line=len(raw_code.splitlines()),
        )
        return

    chunks = _try_treesitter_parse(raw_code, language)
    if chunks is None:
        log.info(f"Tree-sitter unavailable for '{language}' — using line splitter fallback.")
        chunks = _line_splitter_parse(raw_code, language)

    if not chunks:
        # Whole-file fallback: nothing was detected
        yield CodeChunk(
            node_type="file",
            name="<whole_file>",
            code_string=raw_code,
            start_line=1,
            end_line=len(raw_code.splitlines()),
        )
        return

    yield from chunks
