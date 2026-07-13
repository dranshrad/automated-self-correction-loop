# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from ascl.ast_diff import code_hash, compute_structural_diff, normalize_source


def test_structural_diff_detects_modified_function() -> None:
    prev = "def add(a, b):\n    return a - b\n"
    curr = "def add(a, b):\n    return a + b\n"
    diff = compute_structural_diff(prev, curr)
    assert diff.modified == ("add",)
    assert diff.added == ()
    assert "modified: add" in diff.format_block(iteration=2)


def test_structural_diff_detects_added_and_removed() -> None:
    prev = "def foo():\n    return 1\n"
    curr = "def bar():\n    return 2\n"
    diff = compute_structural_diff(prev, curr)
    assert diff.removed == ("foo",)
    assert diff.added == ("bar",)


def test_code_hash_normalizes_trailing_whitespace() -> None:
    assert code_hash("print(1)\n") == code_hash("print(1)  \n")
    assert normalize_source("a  \n") == "a"


def test_structural_diff_syntax_error() -> None:
    diff = compute_structural_diff("def ok():\n    return 1\n", "def bad(\n")
    assert diff.parse_error is not None
    assert "SyntaxError" in diff.format_block()
