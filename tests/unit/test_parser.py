# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest

from ascl.parser import CodeParseError, extract_code_blocks, extract_python_code


def test_extract_python_fence() -> None:
    text = "Sure.\n```python\nprint(1)\n```\n"
    assert extract_python_code(text) == "print(1)"


def test_prefers_python_over_other_fences() -> None:
    text = "```bash\necho hi\n```\n```python\nx = 1\n```"
    assert extract_python_code(text) == "x = 1"


def test_unlabeled_fence_accepted() -> None:
    text = "```\ndef f():\n    return 1\n```"
    assert "def f()" in extract_python_code(text)


def test_fallback_raw_python() -> None:
    text = "def add(a, b):\n    return a + b\n"
    assert "return a + b" in extract_python_code(text)


def test_missing_code_raises() -> None:
    with pytest.raises(CodeParseError):
        extract_python_code("I cannot help with that.")


def test_extract_code_blocks_metadata() -> None:
    blocks = extract_code_blocks("```py\nprint(2)\n```")
    assert len(blocks) == 1
    assert blocks[0].preferred is True
    assert blocks[0].code == "print(2)"
