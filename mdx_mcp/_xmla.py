"""Minimal, dependency-free XMLA (SOAP) client — cross-platform.

Talks to any XMLA endpoint (SSAS multidimensional over HTTP/msmdpump, Mondrian, etc.)
using only the stdlib (urllib). Three operations:

* ``execute(mdx)``  — an ``Execute`` command; returns the first cell value (scalar answers).
* ``execute_cells(mdx)`` — the same ``Execute`` command, but decodes the FULL cellset (every
  axis-member tuple + value) — rankings/breakdowns, not just "one number".
* ``discover(rowset, restrictions)`` — a ``Discover`` request; returns a list of row dicts
  (used by the introspector to read cube schema rowsets).

Most NL→MDX questions target "one number", so ``execute`` parses only the first
``<Cell><Value>`` from the returned mddataset — cheap and sufficient for scalar answers.
``execute_cells`` is the full cellset reader for when the answer is a list, not a scalar.
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

    def execute_cells(self, mdx: str) -> "list":
        """Run an MDX statement; return the FULL cellset as ordered ``Cell`` records.

        Companion to :meth:`execute` for multi-cell results (rankings/breakdowns) — same
        request, but every cell is decoded instead of only the first.
        """
        body = (
            f'<Execute xmlns="{_XMLA}">'
            f"<Command><Statement>{_xml_escape(mdx)}</Statement></Command>"
            f"{self._props()}</Execute>"
        )
        root = self._post(body, "Execute")
        return parse_cells(root)

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


def parse_cells(root: ET.Element) -> "list":
    """Return EVERY cell in an mddataset as ordered ``Cell`` records (full cellset).

    Companion to ``parse_first_cell``: that function deliberately parses only the sole
    cell of a scalar answer; this one decodes the whole result — the shape a
    ranking/breakdown query returns.

    XMLA reports axis member captions separately from cell values: ``<Axes>`` holds one
    ``<Axis>`` per query axis (``Axis0``, ``Axis1``, ... in order; ``SlicerAxis`` — the
    WHERE clause — is excluded, since it is constant across every cell and not part of any
    cell's identity), each with its ``<Tuple>``s of ``<Member><Caption>``. ``<CellData>``
    then holds one ``<Cell CellOrdinal="N">`` per cell. ``CellOrdinal`` is a mixed-radix
    index over the axis sizes with Axis0 varying fastest (the XMLA convention); this
    decodes that ordinal back into a per-axis tuple index and concatenates each axis's
    member captions (Axis0 first, then Axis1, ...) into the cell's ``members`` tuple.
    """
    from .executor import Cell  # deferred: executor.py imports this module at load time

    axes = _parse_axes(root)
    sizes = [len(a) for a in axes]

    cells: list[Cell] = []
    for position, cell_el in enumerate(_iter_cell_elements(root)):
        ordinal_attr = cell_el.get("CellOrdinal")
        ordinal = int(ordinal_attr) if ordinal_attr is not None else position
        members: list[str] = []
        remainder = ordinal
        for axis_tuples, size in zip(axes, sizes):
            if size == 0:
                continue
            idx = remainder % size
            remainder //= size
            members.extend(axis_tuples[idx])
        cells.append(Cell(members=tuple(members), value=_cell_value(cell_el)))
    return cells


def _iter_cell_elements(root: ET.Element) -> list[ET.Element]:
    """All ``<Cell>`` elements under ``<CellData>``, in document order."""
    return [el for el in root.iter() if _local(el.tag) == "Cell"]


def _parse_axes(root: ET.Element) -> "list[list[tuple[str, ...]]]":
    """Non-slicer ``<Axis>``es, each as an ordered list of per-tuple member captions."""
    axes_el = None
    for el in root.iter():
        if _local(el.tag) == "Axes":
            axes_el = el
            break
    if axes_el is None:
        return []
    axes: list[list[tuple[str, ...]]] = []
    for axis in axes_el:
        if _local(axis.tag) != "Axis" or axis.get("name") == "SlicerAxis":
            continue
        tuples: list[tuple[str, ...]] = []
        for tuple_el in axis.iter():
            if _local(tuple_el.tag) != "Tuple":
                continue
            captions = []
            for member in tuple_el:
                if _local(member.tag) != "Member":
                    continue
                captions.append(_member_caption(member))
            tuples.append(tuple(captions))
        axes.append(tuples)
    return axes


def _member_caption(member: ET.Element) -> str:
    for child in member:
        if _local(child.tag) == "Caption":
            return (child.text or "").strip()
    return ""


def _cell_value(cell_el: ET.Element) -> Optional[float]:
    for child in cell_el:
        if _local(child.tag) == "Value":
            text = (child.text or "").strip()
            if text == "":
                return None
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
