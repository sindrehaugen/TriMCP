"""
Phase 3.2: AST-Aware Code Parser
Parses source files into function/class chunks using Tree-sitter.
Falls back to a line-based splitter if Tree-sitter bindings are unavailable.
Yields CodeChunk objects consumed by TriStackEngine.index_code_file().
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

log = logging.getLogger("tri-stack-ast")

SUPPORTED_LANGUAGES = ("python", "javascript", "typescript", "go", "rust")


@dataclass
class CodeChunk:
    node_type: str  # 'function' | 'class' | 'block'
    name: str
    code_string: str
    start_line: int
    end_line: int


# --- Tree-sitter backend (active when packages are installed) ---


def _try_treesitter_parse(raw_code: str, language: str) -> list[CodeChunk] | None:
    """
    Attempt Tree-sitter parse via tree-sitter-language-pack (enterprise bundle).
    Returns None if the pack is missing or the grammar cannot load so the
    caller can fall back gracefully — no hard import-time crash.
    """
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return None

    try:
        from tree_sitter_language_pack import has_language as _pack_has_language
    except ImportError:
        from typing import get_args

        from tree_sitter_language_pack import SupportedLanguage

        _ALLOWED_PACK = frozenset(get_args(SupportedLanguage))

        def _pack_has_language(name: str) -> bool:
            return name in _ALLOWED_PACK

    if not _pack_has_language(language):
        log.warning("Tree-sitter language pack has no grammar for %r", language)
        return None

    try:
        parser = get_parser(language)
        tree = parser.parse(raw_code.encode("utf-8"))
    except Exception as e:
        log.warning("Tree-sitter language pack failed for %r: %s", language, e)
        return None

    # Node types that represent meaningful semantic boundaries
    target_types = {
        "python": {"function_definition", "class_definition"},
        "javascript": {
            "function_declaration",
            "function_expression",
            "arrow_function",
            "class_declaration",
            "method_definition",
        },
        "typescript": {
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "method_definition",
            "interface_declaration",
            "type_alias_declaration",
        },
        "go": {"function_declaration", "method_declaration", "type_declaration"},
        "rust": {"function_item", "struct_item", "enum_item", "impl_item", "trait_item"},
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
            start = node.start_point[0]  # 0-indexed
            end = node.end_point[0]
            code_string = "\n".join(lines[start : end + 1])
            node_type = "function" if "function" in node.type else "class"
            chunks.append(
                CodeChunk(
                    node_type=node_type,
                    name=_extract_name(node),
                    code_string=code_string,
                    start_line=start + 1,  # 1-indexed for storage
                    end_line=end + 1,
                )
            )
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return chunks if chunks else None


# --- Public API ---


def parse_file(raw_code: str, language: str) -> Iterator[CodeChunk]:
    """
    Parse source code into CodeChunk objects.
    Tries Tree-sitter first; falls back to whole-file chunk if unavailable.
    """
    if language not in SUPPORTED_LANGUAGES:
        log.warning("Language %r not supported — yielding single whole-file chunk.", language)
        yield CodeChunk(
            node_type="file",
            name="<whole_file>",
            code_string=raw_code,
            start_line=1,
            end_line=len(raw_code.splitlines()),
        )
        return

    chunks = _try_treesitter_parse(raw_code, language)

    if not chunks:
        # Whole-file fallback: nothing was detected or tree-sitter failed
        yield CodeChunk(
            node_type="file",
            name="<whole_file>",
            code_string=raw_code,
            start_line=1,
            end_line=len(raw_code.splitlines()),
        )
        return

    yield from chunks
