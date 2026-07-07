"""Verification — the ``Verifier`` seam + a self-consistency default.

The OSS goes exactly this deep: run the *k* candidate queries and, if enough of them AGREE
(within a relative tolerance) on the same cell value, answer; otherwise **abstain** or
**clarify**. It does NOT calibrate confidence — a proprietary calibrated trust gate can
replace this via the ``Verifier`` seam.

Honesty rules this default enforces:
  * requires at least ``min_executed`` corroborating candidates before it will answer — one
    un-cross-checked value is not "self-consistent";
  * distinguishes a real failure (endpoint down / bad MDX) from genuine no-data/ambiguity, and
    reports *why* it abstained in ``note`` + an ``errors`` count;
  * clusters values by relative tolerance (not sig-fig string bucketing) so a small money gap
    isn't called agreement and two near-equal values aren't called divergence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ._xmla import XMLAError
from .executor import MdxExecutor, UnsafeMdxError


@dataclass
class Answer:
    """Result of verifying candidate MDX queries against the cube."""

    status: str                    # "answer" | "abstain" | "clarify"
    value: Optional[float] = None  # the agreed cell value when status == "answer"
    mdx: Optional[str] = None      # the MDX that produced the agreed value
    agreement: float = 0.0         # fraction of executed candidates in the modal cluster
    executed: int = 0              # candidates that returned a value
    errors: int = 0               # candidates that raised an execution error (down/bad-MDX)
    candidates: int = 0            # candidates offered
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status, "value": self.value, "mdx": self.mdx,
            "agreement": round(self.agreement, 4), "executed": self.executed,
            "errors": self.errors, "candidates": self.candidates, "note": self.note,
        }


@runtime_checkable
class Verifier(Protocol):
    """Turn candidate MDX into a verified :class:`Answer`."""

    def verify(self, candidates: list[str], executor: MdxExecutor) -> Answer:  # pragma: no cover
        ...


def _cluster(pairs: list[tuple[str, float]], rel_tol: float, abs_tol: float) -> list[list[tuple[str, float]]]:
    """Group (mdx, value) pairs into clusters of numerically-close values."""
    clusters: list[list[tuple[str, float]]] = []
    for mdx, v in pairs:
        for c in clusters:
            if math.isclose(v, c[0][1], rel_tol=rel_tol, abs_tol=abs_tol):
                c.append((mdx, v))
                break
        else:
            clusters.append([(mdx, v)])
    return clusters


class SelfConsistencyVerifier:
    """Run k candidates; a tolerant-majority cluster → answer, else abstain/clarify.

    ``min_agreement`` is the fraction of *executed* candidates that must land in the modal
    value-cluster. ``min_executed`` is the minimum number of candidates that must return a
    value before an answer is allowed (default 2 — one value can't corroborate itself).
    """

    def __init__(self, min_agreement: float = 0.6, min_executed: int = 2,
                 rel_tol: float = 1e-6, abs_tol: float = 1e-9) -> None:
        self.min_agreement = min_agreement
        self.min_executed = max(1, min_executed)
        self.rel_tol = rel_tol
        self.abs_tol = abs_tol

    def verify(self, candidates: list[str], executor: MdxExecutor) -> Answer:
        n = len(candidates)
        executed: list[tuple[str, float]] = []
        errors = 0
        last_err = ""
        for mdx in candidates:
            try:
                v = executor.run(mdx)
            except (UnsafeMdxError, XMLAError) as exc:  # expected failures don't vote…
                errors += 1
                last_err = str(exc)
                continue
            # NOTE: any OTHER exception is a real bug and is intentionally NOT swallowed.
            if v is not None:
                executed.append((mdx, v))

        if not executed:
            if not candidates:
                note = "no MDX candidates were generated (check the LLM / configuration)"
            elif errors:
                note = f"all {errors} candidate(s) failed to execute: {last_err}"
            else:
                note = "candidates ran but returned no value (cube has no data for this?)"
            return Answer("abstain", candidates=n, executed=0, errors=errors, note=note)

        clusters = _cluster(executed, self.rel_tol, self.abs_tol)
        modal = max(clusters, key=len)
        agreement = len(modal) / len(executed)

        if len(executed) < self.min_executed:
            return Answer("abstain", candidates=n, executed=len(executed), errors=errors,
                          note=f"only {len(executed)} candidate(s) corroborated "
                               f"(need {self.min_executed}); not enough to self-verify")
        if agreement >= self.min_agreement:
            mdx, value = modal[0]
            return Answer("answer", value=value, mdx=mdx, agreement=agreement,
                          executed=len(executed), errors=errors, candidates=n)
        status = "clarify" if len(clusters) >= 2 else "abstain"
        return Answer(status, agreement=agreement, executed=len(executed), errors=errors,
                      candidates=n, note="candidates disagreed; question may be ambiguous"
                      if status == "clarify" else "insufficient agreement")
