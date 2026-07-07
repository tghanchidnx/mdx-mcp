"""Minimal, dependency-free XMLA (SOAP) client — cross-platform.

Talks to any XMLA endpoint (SSAS multidimensional over HTTP/msmdpump, Mondrian, etc.)
using only the stdlib (urllib). Two operations:

* ``execute(mdx)``  — an ``Execute`` command; returns the first cell value (scalar answers).
* ``discover(rowset, restrictions)`` — a ``Discover`` request; returns a list of row dicts
  (used by the introspector to read cube schema rowsets).

Scalar-answer focus: NL→MDX questions target "one number", so ``execute`` parses the first
``<Cell><Value>`` from the returned mddataset. Not a full cellset reader — by design.
"""
from __future__ import annotations

import base64
import urllib.request
from typing import Any, Optional
from xml.etree import ElementTree as ET

_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
_XMLA = "urn:schemas-microsoft-com:xml-analysis"
_MDD = "urn:schemas-microsoft-com:xml-analysis:mddataset"
_ROW = "urn:schemas-microsoft-com:xml-analysis:rowset"


class XMLAError(RuntimeError):
    """An XMLA transport/SOAP fault or unparneable response."""


class XMLAClient:
    """A tiny SOAP XMLA client. ``endpoint`` is the msmdpump/XMLA URL; ``catalog`` the DB."""

    def __init__(self, endpoint: str, catalog: str, *, username: Optional[str] = None,
                 password: Optional[str] = None, timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.catalog = catalog
        self.timeout = timeout
        self._auth = None
        if username is not None:
            raw = f"{username}:{password or ''}".encode("utf-8")
            self._auth = "Basic " + base64.b64encode(raw).decode("ascii")

    # -- transport ---------------------------------------------------------
    def _post(self, soap_body: str, soap_action: str) -> ET.Element:
        envelope = (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<Envelope xmlns="{_ENV}"><Body>{soap_body}</Body></Envelope>'
        ).encode("utf-8")
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{_XMLA}:{soap_action}"',
        }
        if self._auth:
            headers["Authorization"] = self._auth
        req = urllib.request.Request(self.endpoint, data=envelope, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except Exception as exc:  # transport failure
            raise XMLAError(f"XMLA POST to {self.endpoint} failed: {exc}") from exc
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise XMLAError(f"unparseable XMLA response: {exc}") from exc
        fault = root.find(f".//{{{_ENV}}}Fault")
        if fault is not None:
            msg = "".join(fault.itertext()).strip()
            raise XMLAError(f"XMLA SOAP fault: {msg[:300]}")
        # SSAS reports query errors IN-BAND (HTTP 200) as <Messages><Error .../></Messages>,
        # not as a SOAP Fault — surface those instead of laundering them into a silent None.
        for el in root.iter():
            if _local(el.tag) in ("Error", "Exception"):
                desc = el.get("Description") or "".join(el.itertext()).strip()
                raise XMLAError(f"XMLA query error: {desc[:300]}")
        return root

    def _props(self, extra: str = "") -> str:
        return (
            "<Properties><PropertyList>"
            f"<Catalog>{self.catalog}</Catalog>"
            "<Format>Multidimensional</Format>"
            f"{extra}</PropertyList></Properties>"
        )

    # -- operations --------------------------------------------------------
    def execute(self, mdx: str) -> Optional[float]:
        """Run an MDX statement; return the first cell value as float (or None)."""
        body = (
            f'<Execute xmlns="{_XMLA}">'
            f"<Command><Statement>{_xml_escape(mdx)}</Statement></Command>"
            f"{self._props()}</Execute>"
        )
        root = self._post(body, "Execute")
        return parse_first_cell(root)

    def discover(self, rowset: str, restrictions: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
        """Run a Discover request for a schema rowset; return row dicts."""
        rlist = "".join(f"<{k}>{_xml_escape(v)}</{k}>" for k, v in (restrictions or {}).items())
        body = (
            f'<Discover xmlns="{_XMLA}">'
            f"<RequestType>{rowset}</RequestType>"
            f"<Restrictions><RestrictionList>{rlist}</RestrictionList></Restrictions>"
            f"{self._props()}</Discover>"
        )
        root = self._post(body, "Discover")
        return parse_rowset(root)


# -- pure parsers (unit-tested without a live server) ----------------------
def parse_first_cell(root: ET.Element) -> Optional[float]:
    """Return the sole ``<Cell><Value>`` in an mddataset as float, or None.

    A multi-cell result means the MDX was not the single-cell query we asked for — return
    None (a non-scalar must not silently 'vote' as if it were one value).
    """
    cells = [c for c in root.iter() if _local(c.tag) == "Cell"]
    if len(cells) > 1:
        return None
    for value in root.iter(f"{{{_MDD}}}Value"):
        text = (value.text or "").strip()
        if text == "":
            return None
        try:
            return float(text)
        except ValueError:
            return None
    # namespace-agnostic fallback (some servers vary the mddataset ns)
    for cell in root.iter():
        if cell.tag.endswith("}Value") or cell.tag == "Value":
            text = (cell.text or "").strip()
            try:
                return float(text)
            except ValueError:
                return None
    return None


def parse_rowset(root: ET.Element) -> list[dict[str, Any]]:
    """Return the rows of a Discover rowset as a list of {col: text} dicts."""
    rows: list[dict[str, Any]] = []
    for row in root.iter(f"{{{_ROW}}}row"):
        rows.append({_local(child.tag): (child.text or "").strip() for child in row})
    if not rows:  # ns-agnostic fallback
        for el in root.iter():
            if _local(el.tag) == "row" and len(list(el)):
                rows.append({_local(c.tag): (c.text or "").strip() for c in el})
    return rows


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
