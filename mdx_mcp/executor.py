"""MDX execution — the ``MdxExecutor`` seam + a cross-platform XMLA executor.

``MdxExecutor`` is the open-core seam: swap the backend without touching the engine.
``safe_mdx`` is a read-only guard — only ``SELECT``/``WITH`` MDX is allowed to execute.
An optional ADOMD backend (Windows/.NET) can be added by implementing the same Protocol.
"""
from __future__ import annotations

import re
from typing import Optional, Protocol, runtime_checkable

from ._xmla import XMLAClient

# MDX write/DDL/admin verbs that must never execute through this read-only tool.
_FORBIDDEN = re.compile(
    r"\b(CREATE|ALTER|DROP|DELETE|UPDATE|INSERT|CALL|EXECUTE|GRANT|REVOKE)\b", re.IGNORECASE
)


class UnsafeMdxError(ValueError):
    """Raised when an MDX statement is not a read-only SELECT/WITH query."""


def safe_mdx(mdx: str) -> str:
    """Return the MDX if it is a read-only query, else raise ``UnsafeMdxError``."""
    text = (mdx or "").strip().rstrip(";").strip()
    if not text:
        raise UnsafeMdxError("empty MDX")
    head = text.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise UnsafeMdxError("only SELECT/WITH MDX may run (read-only)")
    if _FORBIDDEN.search(text):
        raise UnsafeMdxError("MDX contains a forbidden write/DDL/admin keyword")
    return text


@runtime_checkable
class MdxExecutor(Protocol):
    """Execute a read-only MDX statement, returning the first cell as float | None."""

    def run(self, mdx: str) -> Optional[float]:  # pragma: no cover - protocol
        ...


class XMLAExecutor:
    """Cross-platform MDX executor over XMLA/SOAP. Guards every statement with ``safe_mdx``."""

    def __init__(self, endpoint: str, catalog: str, *, username: Optional[str] = None,
                 password: Optional[str] = None, timeout: float = 30.0) -> None:
        self._client = XMLAClient(endpoint, catalog, username=username, password=password,
                                  timeout=timeout)

    def run(self, mdx: str) -> Optional[float]:
        return self._client.execute(safe_mdx(mdx))
