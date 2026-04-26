from __future__ import annotations

import ast
import hashlib
import re
import uuid
from pathlib import Path
from typing import Generator

from qdrant_edge_querycode.config import SKIP_DIRS, SKIP_EXTS, CODE_EXTS, MAX_CHUNK_LINES

def _chunk_id(file: str, name: str) -> str:
    raw = f"{file}::{name}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _language(path: Path) -> str:
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".go": "go", ".java": "java", ".rs": "rust", ".rb": "ruby",
        ".cpp": "cpp", ".c": "c", ".cs": "csharp", ".php": "php",
        ".swift": "swift", ".kt": "kotlin",
    }.get(path.suffix.lower(), "unknown")

def _parse_python(source: str, rel_path: str) -> list[dict]:
    chunks: list[dict] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return chunks

    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        name = node.name
        start = node.lineno - 1      # 0-indexed
        end   = node.end_lineno      # 1-indexed (exclusive for slicing)

        code_lines = lines[start:end]

        # If the chunk is too large, grab only the signature + first N lines
        if len(code_lines) > MAX_CHUNK_LINES:
            code_lines = code_lines[:MAX_CHUNK_LINES] + ["    # ... (truncated)"]

        code = "\n".join(code_lines)

        kind = "class" if isinstance(node, ast.ClassDef) else "function"

        chunks.append({
            "id":         _chunk_id(rel_path, f"{kind}:{name}"),
            "name":       name,
            "kind":       kind,
            "code":       code,
            "file":       rel_path,
            "language":   "python",
            "start_line": node.lineno,
            "end_line":   node.end_lineno or node.lineno,
        })

    return chunks

# Patterns ordered by specificity — each must capture group 1 = function/class name
_PATTERNS = [
    # Go:   func (r *Receiver) MethodName(
    (re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.MULTILINE), "function"),
    # Java/Kotlin/C#: public/private/protected ... Type functionName(
    (re.compile(r"(?:public|private|protected|static|async)\s+[\w\[\]<>]+\s+(\w+)\s*\(", re.MULTILINE), "function"),
    # JS/TS: function name( or async function name(
    (re.compile(r"(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE), "function"),
    # JS/TS: const/let name = (async)? (...) =>
    (re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(", re.MULTILINE), "function"),
    # JS/TS: methodName( — inside a class (lines that start with word char)
    (re.compile(r"^\s{2,}(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE), "function"),
    # class Name extends / implements
    (re.compile(r"(?:class|interface)\s+(\w+)", re.MULTILINE), "class"),
    # Rust: fn function_name(
    (re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]", re.MULTILINE), "function"),
    # Ruby: def method_name
    (re.compile(r"^\s*def\s+(\w+)", re.MULTILINE), "function"),
]

_CONTEXT_LINES = 30  

def _parse_generic(source: str, rel_path: str, lang: str) -> list[dict]:
    chunks: list[dict] = []
    lines  = source.splitlines()
    seen   : set[str] = set()

    for pattern, kind in _PATTERNS:
        for m in pattern.finditer(source):
            name = m.group(1)
            if name in {"if", "else", "for", "while", "return", "new",
                        "true", "false", "null", "None", "self", "this"}:
                continue

            line_no = source[:m.start()].count("\n") + 1   # 1-indexed
            key     = f"{kind}:{name}:{line_no}"
            if key in seen:
                continue
            seen.add(key)

            start_idx = line_no - 1
            end_idx   = min(start_idx + _CONTEXT_LINES, len(lines))
            code      = "\n".join(lines[start_idx:end_idx])

            chunks.append({
                "id":         _chunk_id(rel_path, key),
                "name":       name,
                "kind":       kind,
                "code":       code,
                "file":       rel_path,
                "language":   lang,
                "start_line": line_no,
                "end_line":   end_idx,
            })

    return chunks

def iter_chunks(repo_root: str | Path) -> Generator[dict, None, None]:
    """
    Walk *repo_root* and yield code chunks for every parseable file.
    """
    root  = Path(repo_root).resolve()

    for path in root.rglob("*"):

        if path.is_dir():
            continue


        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue


        if path.suffix.lower() in SKIP_EXTS:
            continue
        if path.suffix.lower() not in CODE_EXTS:
            continue

        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if not source.strip():
            continue

        rel_str = str(rel)
        lang    = _language(path)

        if lang == "python":
            chunks = _parse_python(source, rel_str)
        else:
            chunks = _parse_generic(source, rel_str, lang)


        if not chunks:
            lines = source.splitlines()[:MAX_CHUNK_LINES]
            chunks = [{
                "id":         _chunk_id(rel_str, "file"),
                "name":       path.stem,
                "kind":       "file",
                "code":       "\n".join(lines),
                "file":       rel_str,
                "language":   lang,
                "start_line": 1,
                "end_line":   len(lines),
            }]

        yield from chunks
