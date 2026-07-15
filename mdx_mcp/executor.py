"""MDX execution — the ``MdxExecutor`` seam + a cross-platform XMLA executor.

``MdxExecutor`` is the open-core seam: swap the backend without touching the engine.
``safe_mdx`` is a read-only guard — only ``SELECT``/``WITH`` MDX is allowed to execute.
An optional ADOMD backend (Windows/.NET) can be added by implementing the same Protocol.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ._xmla import XMLAClient

# MDX/XMLA write/DDL/admin/script verbs that must never execute through this read-only tool.
# SCOPE is an MDX-script assignment verb (mutates cell values) — explicitly denied.
_FORBIDDEN = re.compile(
    r"\b(CREATE|ALTER|DROP|DELETE|UPDATE|INSERT|CALL|EXECUTE|GRANT|REVOKE|SCOPE)\b", re.IGNORECASE
)
# Comments (whitespace to the server) — stripped so a split keyword can't hide a verb.
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*|--[^\n]*", re.DOTALL)
# Bracketed identifiers and string literals — masked so member NAMES that contain a keyword
# (e.g. [Drop-off Rate], [Update Log]) don't false-trip the denylist / statement split.
_BRACKET = re.compile(r"\[[^\]]*\]")
_STRING = re.compile(r"'[^']*'|\"[^\"]*\"")


class UnsafeMdxError(ValueError):
    """Raised when an MDX statement is not a single read-only SELECT/WITH query."""


def safe_mdx(mdx: str) -> str:
    """Return the MDX if it is a SINGLE read-only query, else raise ``UnsafeMdxError``.

    Defense is structural: mask identifiers/strings + strip comments, require exactly one
    statement, require the head to be SELECT/WITH, and deny write/script verbs. Masking is
    validation-only — the ORIGINAL text is returned for execution.
    """
    text = (mdx or "").strip().rstrip(";").strip()
    if not text:
        raise UnsafeMdxError("empty MDX")
    # Build a masked view for inspection ONLY (never executed).
    masked = _COMMENTS.sub(" ", text)
    masked = _BRACKET.sub(" [ID] ", masked)
    masked = _STRING.sub(" '' ", masked)
    # A remaining ';' means statement batching — the SCOPE/write-injection vector. Reject.
    if ";" in masked:
        raise UnsafeMdxError("only a single MDX statement may run (read-only)")
    head = masked.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise UnsafeMdxError("only SELECT/WITH MDX may run (read-only)")
    if _FORBIDDEN.search(masked):
        raise UnsafeMdxError("MDX contains a forbidden write/DDL/admin keyword")
    return text


@dataclass(frozen=True)
class Cell:
    """One cell of a full MDX cellset: its axis-member captions + numeric value.

    ``members`` is the tuple of member captions (Axis0 first, then Axis1, ...; the
    slicer/WHERE axis is never included) that this cell's coordinates resolve to.
    ``value`` mirrors the scalar ``run`` contract: ``None`` for an empty/non-numeric cell.
    """

    members: tuple[str, ...]
    value: Optional[float]


@runtime_checkable
class MdxExecutor(Protocol):
    """Execute a read-only MDX statement, returning the first cell as float | None."""

    def run(self, mdx: str) -> Optional[float]:  # pragma: no cover - protocol
        ...

    def run_cells(self, mdx: str) -> list[Cell]:  # pragma: no cover - protocol
        """Execute a read-only MDX statement, returning the FULL cellset (all cells)."""
        ...


class XMLAExecutor:
    """Cross-platform MDX executor over XMLA/SOAP. Guards every statement with ``safe_mdx``."""

    def __init__(self, endpoint: str, catalog: str, *, username: Optional[str] = None,
                 password: Optional[str] = None, timeout: float = 30.0) -> None:
        self._client = XMLAClient(endpoint, catalog, username=username, password=password,
                                  timeout=timeout)

    def run(self, mdx: str) -> Optional[float]:
        return self._client.execute(safe_mdx(mdx))

    def run_cells(self, mdx: str) -> list[Cell]:
        return self._client.execute_cells(safe_mdx(mdx))
