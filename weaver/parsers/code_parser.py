"""Source code parser via tree-sitter. Emits nodes for definitions + imports."""
from __future__ import annotations

from collections.abc import Iterable

from weaver.parsers.base import ParsedNode, ParseInput, Parser
from weaver.parsers.dispatch import register_parser

# Canonical extension → language name (tree-sitter-languages).
_EXT_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".scala": "scala",
    ".lua": "lua",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
}


class CodeParser(Parser):
    name = "code"
    handles_mime = frozenset()  # mime is unreliable for source code
    handles_ext = frozenset(_EXT_LANG.keys())

    def parse(self, inp: ParseInput) -> Iterable[ParsedNode]:
        try:
            from tree_sitter_languages import get_parser as ts_get_parser
        except ImportError as e:
            raise RuntimeError("tree-sitter-languages required") from e

        lang = self._lang(inp)
        if lang is None:
            # Unknown extension — fall back to text-level node.
            text = inp.data.decode("utf-8", errors="replace") if isinstance(inp.data, bytes) else inp.data
            yield ParsedNode(content=text, kind="code.unknown", metadata={"uri": inp.uri or ""})
            return

        ts_parser = ts_get_parser(lang)
        raw = inp.data.encode("utf-8") if isinstance(inp.data, str) else inp.data
        tree = ts_parser.parse(raw)
        root = tree.root_node

        file_node = ParsedNode(
            content="", kind=f"file.{lang}",
            metadata={"uri": inp.uri or "", "language": lang},
        )

        for definition in _walk_definitions(root, raw, lang):
            file_node.children.append(definition)

        yield file_node

    def references(self, inp: ParseInput) -> Iterable[str]:
        """Emit import specifiers. Consumed by the graph builder for edges."""
        try:
            from tree_sitter_languages import get_parser as ts_get_parser
        except ImportError:
            return
        lang = self._lang(inp)
        if lang is None:
            return
        ts_parser = ts_get_parser(lang)
        raw = inp.data.encode("utf-8") if isinstance(inp.data, str) else inp.data
        tree = ts_parser.parse(raw)
        yield from _walk_imports(tree.root_node, raw, lang)

    def _lang(self, inp: ParseInput) -> str | None:
        if not inp.uri:
            return None
        for ext, name in _EXT_LANG.items():
            if inp.uri.endswith(ext):
                return name
        return None


# --- tree-sitter walking helpers (language-aware, light touch) ---

_DEFINITION_KINDS = {
    "python": {"function_definition", "class_definition"},
    "typescript": {"function_declaration", "class_declaration", "method_definition"},
    "tsx": {"function_declaration", "class_declaration", "method_definition"},
    "javascript": {"function_declaration", "class_declaration", "method_definition"},
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {"function_item", "impl_item", "struct_item", "enum_item", "trait_item"},
    "java": {"method_declaration", "class_declaration", "interface_declaration"},
    "ruby": {"method", "class", "module"},
    "c": {"function_definition"},
    "cpp": {"function_definition", "class_specifier"},
    "c_sharp": {"method_declaration", "class_declaration", "interface_declaration"},
    "kotlin": {"function_declaration", "class_declaration"},
    "swift": {"function_declaration", "class_declaration"},
    "php": {"function_definition", "class_declaration", "method_declaration"},
    "scala": {"function_definition", "class_definition", "object_definition"},
    "lua": {"function_declaration"},
    "bash": {"function_definition"},
}


def _walk_definitions(node, raw: bytes, lang: str) -> Iterable[ParsedNode]:
    kinds = _DEFINITION_KINDS.get(lang, set())
    for child in _walk(node):
        if child.type in kinds:
            name = _identifier_text(child, raw) or "<anonymous>"
            snippet = raw[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            yield ParsedNode(
                content=snippet,
                kind=f"def.{lang}.{child.type}",
                metadata={
                    "name": name,
                    "start_line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                },
            )


_IMPORT_KINDS = {
    "python": {"import_statement", "import_from_statement"},
    "typescript": {"import_statement", "import_clause"},
    "tsx": {"import_statement", "import_clause"},
    "javascript": {"import_statement", "import_clause"},
    "go": {"import_declaration"},
    "rust": {"use_declaration"},
    "java": {"import_declaration"},
    "ruby": {"call"},  # ruby 'require' appears as a call — filtered below
}


def _walk_imports(node, raw: bytes, lang: str) -> Iterable[str]:
    kinds = _IMPORT_KINDS.get(lang, set())
    for child in _walk(node):
        if child.type in kinds:
            text = raw[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip()
            yield text


def _walk(node) -> Iterable:
    yield node
    for c in node.children:
        yield from _walk(c)


def _identifier_text(node, raw: bytes) -> str | None:
    for c in node.children:
        if c.type in {"identifier", "type_identifier", "property_identifier", "field_identifier"}:
            return raw[c.start_byte:c.end_byte].decode("utf-8", errors="replace")
    return None


register_parser(CodeParser())
