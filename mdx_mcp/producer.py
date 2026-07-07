"""NL→MDX producer — generate *k* diverse candidate MDX queries for a question.

Grounds the model in a ``cube_skills`` block (from the introspector) and asks for one
single-cell ``SELECT`` per candidate, under a different "lens" each time so an ambiguous
question yields divergent MDX (which the verifier then abstains/clarifies on). Pure text
generation via the injected ``LLMClient`` — no execution here.
"""
from __future__ import annotations

import re
from typing import Optional

from .llm import LLMClient

# Distinct angles so candidates are genuinely diverse, not k identical samples.
_LENSES = [
    "the most direct reading of the question",
    "an alternate measure or aggregation if the question is ambiguous",
    "an explicit member/time context you infer from the question",
    "the simplest possible query that still answers it",
    "a defensive reading that names the default member explicitly",
]

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|```$", re.MULTILINE)


def extract_mdx(raw: str) -> str:
    """Strip markdown fences / stray prose, returning the bare MDX statement."""
    text = _FENCE.sub("", raw or "").strip()
    # keep from the first SELECT/WITH onward if the model added a preamble
    m = re.search(r"(?is)\b(with|select)\b", text)
    if m:
        text = text[m.start():]
    return text.strip().rstrip(";").strip()


def _prompt(question: str, cube_skills: str, lens: str) -> str:
    parts = []
    if cube_skills.strip():
        parts.append("You are querying this OLAP cube:\n" + cube_skills.strip())
    parts.append(f"Question: {question}")
    parts.append(f"Write MDX using {lens}.")
    parts.append("Reply with ONLY the MDX — a single SELECT that yields ONE cell "
                 "(one measure on COLUMNS, the relevant context in WHERE). No prose, no code fences.")
    return "\n\n".join(parts)


class MdxProducer:
    """Generate candidate MDX queries for a natural-language question."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def candidates(self, question: str, cube_skills: str = "", k: int = 3) -> list[str]:
        out: list[str] = []
        for i in range(max(1, k)):
            lens = _LENSES[i % len(_LENSES)]
            try:
                raw = self._llm.complete(_prompt(question, cube_skills, lens))
            except Exception:
                continue
            mdx = extract_mdx(raw)
            if mdx:
                out.append(mdx)
        return out
