"""Verification — the ``Verifier`` seam + a self-consistency default.

The OSS goes exactly this deep: run the *k* candidate queries, and if a majority agree
on the same cell value, answer; otherwise **abstain** (or **clarify**). It does NOT calibrate
confidence — a proprietary calibrated trust gate can replace this via the ``Verifier`` seam.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .executor import MdxExecutor, UnsafeMdxError


@dataclass
class Answer:
    """Result of verifying candidate MDX queries against the cube."""

    status: str                    # "answer" | "abstain" | "clarify"
    value: Optional[float] = None  # the agreed cell value when status == "answer"
    mdx: Optional[str] = None      # the MDX that produced the agreed value
    agreement: float = 0.0         # fraction of executed candidates that agreed
    executed: int = 0              # how many candidates ran without error
    candidates: int = 0            # how many candidates were offered
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status, "value": self.value, "mdx": self.mdx,
            "agreement": round(self.agreement, 4), "executed": self.executed,
            "candidates": self.candidates, "note": self.note,
        }


class Verifier(Protocol):
    """Turn candidate MDX into a verified :class:`Answer`."""

    def verify(self, candidates: list[str], executor: MdxExecutor) -> Answer:  # pragma: no cover
        ...


def _key(v: Optional[float]) -> str:
    """Bucket a float for agreement (avoid float-equality noise)."""
    if v is None:
        return "∅"
    return f"{v:.6g}"


class SelfConsistencyVerifier:
    """Run k candidates; majority-agreement → answer, else abstain/clarify.

    ``min_agreement`` is the fraction of *executed* candidates that must share the modal
    value to answer. Divergence with ≥2 distinct non-null values → ``clarify`` (the question
    is likely ambiguous); everything else that fails the threshold → ``abstain``.
    """

    def __init__(self, min_agreement: float = 0.6) -> None:
        self.min_agreement = min_agreement

    def verify(self, candidates: list[str], executor: MdxExecutor) -> Answer:
        results: list[tuple[str, Optional[float]]] = []
        for mdx in candidates:
            try:
                results.append((mdx, executor.run(mdx)))
            except (UnsafeMdxError, Exception):
                continue  # a bad candidate just doesn't vote
        executed = [(m, v) for m, v in results if v is not None]
        n_offered = len(candidates)
        if not executed:
            return Answer("abstain", candidates=n_offered, executed=0,
                          note="no candidate produced a value")
        counts = Counter(_key(v) for _, v in executed)
        modal_key, modal_n = counts.most_common(1)[0]
        agreement = modal_n / len(executed)
        if agreement >= self.min_agreement:
            mdx, value = next((m, v) for m, v in executed if _key(v) == modal_key)
            return Answer("answer", value=value, mdx=mdx, agreement=agreement,
                          executed=len(executed), candidates=n_offered)
        status = "clarify" if len({_key(v) for _, v in executed}) >= 2 else "abstain"
        return Answer(status, agreement=agreement, executed=len(executed), candidates=n_offered,
                      note="candidates disagreed; question may be ambiguous"
                      if status == "clarify" else "insufficient agreement")
