"""NL→MDX producer — generate *k* diverse candidate MDX queries for a question.

Grounds the model in a ``cube_skills`` block (from the introspector) and, per the requested
``shape``, asks for either a single-cell ``SELECT`` (``shape="cell"``, the default — a scalar
answer), a cellset-shaped ``SELECT`` with the implied members on ROWS (``shape="cellset"`` —
rankings/breakdowns), or lets the model choose (``shape="auto"``) — under a different "lens"
each time so an ambiguous question yields divergent MDX (which the verifier then
abstains/clarifies on). Pure text generation via the injected ``LLMClient`` — no execution here.
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

# Valid values for the ``shape`` param on MdxProducer.candidates().
_SHAPES = ("cell", "cellset", "auto")


def extract_mdx(raw: str) -> str:
    """Strip markdown fences / stray prose, returning the bare MDX statement.

    Anchors to a statement head at the START of a line (``^\\s*(WITH|SELECT)``) so a prose
    preamble like "I will *select* the measure:\\n\\nSELECT ..." doesn't get matched on the
    prose word. Falls back to the first inline SELECT/WITH only if no line-anchored head
    exists.
    """
    text = _FENCE.sub("", raw or "").strip()
    m = re.search(r"(?im)^\s*(with|select)\b", text)
    if not m:
        m = re.search(r"(?is)\b(with|select)\b", text)  # fallback: single-line output
    if m:
        text = text[m.start():]
    return text.strip().rstrip(";").strip()


def _prompt(question: str, cube_skills: str, lens: str, shape: str = "cell") -> str:
    parts = []
    if cube_skills.strip():
        parts.append("You are querying this OLAP cube:\n" + cube_skills.strip())
    parts.append(f"Question: {question}")
    parts.append(f"Write MDX using {lens}.")
    if shape == "cell":
        parts.append("Reply with ONLY the MDX — a single SELECT that yields ONE cell "
                     "(one measure on COLUMNS, the relevant context in WHERE). No prose, no code fences.")
    elif shape == "cellset":
        parts.append("Reply with ONLY the MDX — a SELECT whose ROWS axis enumerates the members "
                     "the question implies (e.g. TOPCOUNT/ORDER for a ranking, or a hierarchy's "
                     ".MEMBERS for a breakdown), with one measure on COLUMNS and the slicing context "
                     "in WHERE. No prose, no code fences.")
    elif shape == "auto":
        parts.append("Reply with ONLY the MDX that best answers the question — a single-cell SELECT "
                     "(one measure on COLUMNS, context in WHERE) if it asks for one number, or a "
                     "SELECT with a ROWS axis (e.g. TOPCOUNT/ORDER for a ranking, or a hierarchy's "
                     ".MEMBERS for a breakdown) if it asks for a ranking or breakdown — one measure "
                     "on COLUMNS either way. No prose, no code fences.")
    else:
        raise ValueError(f"unknown shape: {shape!r} (expected one of {_SHAPES})")
    return "\n\n".join(parts)


class MdxProducer:
    """Generate candidate MDX queries for a natural-language question."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def candidates(self, question: str, cube_skills: str = "", k: int = 3,
                    shape: str = "cell") -> list[str]:
        """Generate up to *k* candidate MDX strings.

        ``shape`` controls what kind of MDX is requested (see module docstring):
        ``"cell"`` (default, back-compat), ``"cellset"``, or ``"auto"``. Raises
        ``ValueError`` immediately on an unrecognized shape — *before* any LLM call, so
        the error is never swallowed by the per-candidate failure handling below.
        """
        if shape not in _SHAPES:
            raise ValueError(f"unknown shape: {shape!r} (expected one of {_SHAPES})")
        out: list[str] = []
        for i in range(max(1, k)):
            lens = _LENSES[i % len(_LENSES)]
            prompt = _prompt(question, cube_skills, lens, shape)
            try:
                raw = self._llm.complete(prompt)
            except Exception:
                continue
            mdx = extract_mdx(raw)
            if mdx:
                out.append(mdx)
        return out
