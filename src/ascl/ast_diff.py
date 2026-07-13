# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""AST-aware structural diffs for token-efficient correction history."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class StructuralDiff:
    """High-signal summary of what changed between two Python sources."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    modified: tuple[str, ...]
    unchanged: tuple[str, ...]
    parse_error: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.modified) and self.parse_error is None

    def format_block(self, *, iteration: int | None = None) -> str:
        if self.parse_error:
            return f"Structural diff unavailable ({self.parse_error})."
        header = (
            f"In iteration {iteration}, structural changes:"
            if iteration is not None
            else "Structural changes:"
        )
        lines = [header]
        if self.modified:
            lines.append("  modified: " + ", ".join(self.modified))
        if self.added:
            lines.append("  added: " + ", ".join(self.added))
        if self.removed:
            lines.append("  removed: " + ", ".join(self.removed))
        if self.empty:
            lines.append("  (no named top-level defs/classes changed; body may still differ)")
        return "\n".join(lines)


def normalize_source(code: str) -> str:
    """Normalize insignificant whitespace for hashing / comparison."""
    return "\n".join(line.rstrip() for line in code.strip().splitlines())


def code_hash(code: str) -> str:
    """Stable SHA-256 of normalized source."""
    return hashlib.sha256(normalize_source(code).encode("utf-8")).hexdigest()


def compute_structural_diff(previous: str, current: str) -> StructuralDiff:
    """
    Diff top-level functions and classes by qualified name + body fingerprint.

    Nested defs are intentionally ignored so the prompt stays dense and local.
    """
    try:
        prev_map = _top_level_map(previous)
        curr_map = _top_level_map(current)
    except SyntaxError as exc:
        return StructuralDiff(
            added=(),
            removed=(),
            modified=(),
            unchanged=(),
            parse_error=f"SyntaxError: {exc.msg} at line {exc.lineno}",
        )

    prev_names = set(prev_map)
    curr_names = set(curr_map)
    added = tuple(sorted(curr_names - prev_names))
    removed = tuple(sorted(prev_names - curr_names))
    shared = prev_names & curr_names
    modified = tuple(sorted(name for name in shared if prev_map[name] != curr_map[name]))
    unchanged = tuple(sorted(name for name in shared if prev_map[name] == curr_map[name]))
    return StructuralDiff(
        added=added,
        removed=removed,
        modified=modified,
        unchanged=unchanged,
    )


def _top_level_map(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    mapping: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mapping[node.name] = _node_fingerprint(node)
    return mapping


def _node_fingerprint(node: ast.AST) -> str:
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()
