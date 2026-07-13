# SPDX-FileCopyrightText: 2026 Divyansh Gupta
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Extract fenced code blocks from model responses."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE_RE = re.compile(
    r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```",
    re.DOTALL,
)

_PREFERRED_LANGS = frozenset({"python", "py", "python3", ""})


@dataclass(frozen=True)
class ParsedCode:
    """A single extracted code candidate."""

    language: str
    code: str
    preferred: bool


class CodeParseError(ValueError):
    """Raised when no usable code block is found."""


def extract_code_blocks(text: str) -> list[ParsedCode]:
    """Return all fenced code blocks, marking preferred Python fences."""
    blocks: list[ParsedCode] = []
    for match in _FENCE_RE.finditer(text):
        lang = (match.group("lang") or "").strip().lower()
        body = match.group("body").strip("\n")
        if not body.strip():
            continue
        preferred = lang in _PREFERRED_LANGS or lang.startswith("python")
        blocks.append(ParsedCode(language=lang, code=body, preferred=preferred))
    return blocks


def extract_python_code(text: str) -> str:
    """
    Extract the best Python candidate from a model response.

    Preference order:
    1. Explicit python/py fences
    2. Unlabeled fences
    3. Largest remaining fence
    4. Entire response if it looks like Python source
    """
    blocks = extract_code_blocks(text)
    if blocks:
        preferred = [b for b in blocks if b.preferred]
        pool = preferred or blocks
        return max(pool, key=lambda b: len(b.code)).code

    stripped = text.strip()
    if _looks_like_python(stripped):
        return stripped

    raise CodeParseError(
        "No fenced Python code block found in the model response. "
        "Ask the model to return a single ```python``` fence."
    )


def _looks_like_python(text: str) -> bool:
    if not text:
        return False
    indicators = ("def ", "import ", "from ", "class ", "if __name__")
    return any(token in text for token in indicators)
