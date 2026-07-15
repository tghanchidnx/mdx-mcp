"""Cellset reader — ``run_cells`` / ``Cell`` / ``XMLAClient.execute_cells``.

Full-cellset companion to the scalar ``run``/``execute`` path: multi-cell results
(rankings, breakdowns) instead of just the first cell. Offline throughout — the XMLA
transport is mocked (``urllib.request.urlopen``) or the pure SOAP parser is exercised
directly against a canned mddataset fixture, same pattern as ``tests/test_xmla.py``.
"""
import pytest
from xml.etree import ElementTree as ET

from mdx_mcp._xmla import XMLAClient, parse_cells
from mdx_mcp.executor import Cell, MdxExecutor, UnsafeMdxError, XMLAExecutor, safe_mdx

# -- fixtures ---------------------------------------------------------------

# Single axis (Axis0), two tuples — the simple "ranking" shape: one dimension on
# columns, no rows axis. Two axis tuples -> two cells.
_EXECUTE_1AXIS = """<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>
 <ExecuteResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>
  <root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
   <Axes>
    <Axis name="Axis0">
     <Tuples>
      <Tuple><Member Hierarchy="[Customer].[Name]">
       <UName>[Customer].[Name].[Alice]</UName><Caption>Alice</Caption></Member></Tuple>
      <Tuple><Member Hierarchy="[Customer].[Name]">
       <UName>[Customer].[Name].[Bob]</UName><Caption>Bob</Caption></Member></Tuple>
     </Tuples>
    </Axis>
   </Axes>
   <CellData>
    <Cell CellOrdinal="0"><Value>100.5</Value></Cell>
    <Cell CellOrdinal="1"><Value>85</Value></Cell>
   </CellData>
  </root>
 </return></ExecuteResponse>
</Body></Envelope>"""

# Two axes (Axis0 x Axis1), 2x2 — a breakdown, to prove CellOrdinal mixed-radix
# decoding (Axis0 varies fastest) and that the SlicerAxis (WHERE) is excluded.
_EXECUTE_2AXIS = """<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>
 <ExecuteResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>
  <root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
   <Axes>
    <Axis name="Axis0">
     <Tuples>
      <Tuple><Member><Caption>Q1</Caption></Member></Tuple>
      <Tuple><Member><Caption>Q2</Caption></Member></Tuple>
     </Tuples>
    </Axis>
    <Axis name="Axis1">
     <Tuples>
      <Tuple><Member><Caption>East</Caption></Member></Tuple>
      <Tuple><Member><Caption>West</Caption></Member></Tuple>
     </Tuples>
    </Axis>
    <Axis name="SlicerAxis">
     <Tuples>
      <Tuple><Member><Caption>2024</Caption></Member></Tuple>
     </Tuples>
    </Axis>
   </Axes>
   <CellData>
    <Cell CellOrdinal="0"><Value>1</Value></Cell>
    <Cell CellOrdinal="1"><Value>2</Value></Cell>
    <Cell CellOrdinal="2"><Value>3</Value></Cell>
    <Cell CellOrdinal="3"><Value>4</Value></Cell>
   </CellData>
  </root>
 </return></ExecuteResponse>
</Body></Envelope>"""


# -- pure parser: parse_cells (mirrors parse_first_cell, over ALL cells) ----

def test_parse_cells_single_axis_two_tuples():
    cells = parse_cells(ET.fromstring(_EXECUTE_1AXIS))
    assert cells == [
        Cell(members=("Alice",), value=100.5),
        Cell(members=("Bob",), value=85.0),
    ]


def test_parse_cells_two_axes_mixed_radix_and_slicer_excluded():
    cells = parse_cells(ET.fromstring(_EXECUTE_2AXIS))
    # Axis0 (Q1/Q2) varies fastest per XMLA CellOrdinal convention; SlicerAxis (2024)
    # must NOT appear in any member tuple.
    assert cells == [
        Cell(members=("Q1", "East"), value=1.0),
        Cell(members=("Q2", "East"), value=2.0),
        Cell(members=("Q1", "West"), value=3.0),
        Cell(members=("Q2", "West"), value=4.0),
    ]


# -- XMLAClient.execute_cells: offline, transport mocked --------------------

def test_client_execute_cells_offline(monkeypatch):
    class _Resp:
        def read(self):
            return _EXECUTE_1AXIS.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    client = XMLAClient("http://x/olap", "DB")
    cells = client.execute_cells("SELECT [Customer].[Name].Members ON 0 FROM [Cube]")
    assert cells == [
        Cell(members=("Alice",), value=100.5),
        Cell(members=("Bob",), value=85.0),
    ]


# -- XMLAExecutor.run_cells: delegates + guarded by safe_mdx ----------------

def test_executor_run_cells_delegates_to_client(monkeypatch):
    ex = XMLAExecutor("http://x/olap", "DB")
    seen = {}

    def _fake_execute_cells(mdx):
        seen["mdx"] = mdx
        return [Cell(members=("Alice",), value=100.5), Cell(members=("Bob",), value=85.0)]

    monkeypatch.setattr(ex._client, "execute_cells", _fake_execute_cells)
    cells = ex.run_cells("SELECT [Customer].[Name].Members ON 0 FROM [Cube]")
    assert cells == [
        Cell(members=("Alice",), value=100.5),
        Cell(members=("Bob",), value=85.0),
    ]
    assert seen["mdx"] == "SELECT [Customer].[Name].Members ON 0 FROM [Cube]"


def test_executor_run_cells_guards_before_calling_backend(monkeypatch):
    ex = XMLAExecutor("http://x/olap", "DB")
    called = {"n": 0}

    def _boom(mdx):  # the XMLA client must never be hit for unsafe MDX
        called["n"] += 1
        return []

    monkeypatch.setattr(ex._client, "execute_cells", _boom)
    with pytest.raises(UnsafeMdxError):
        ex.run_cells("DROP CUBE [C]")
    assert called["n"] == 0


def test_executor_run_cells_full_chain_two_axis_result(monkeypatch):
    # end-to-end offline: run_cells -> safe_mdx -> client.execute_cells -> _post -> parse_cells,
    # against a REAL 2-axis mddataset (not a pre-built Cell mock) — proves the composed path,
    # not just each link in isolation.
    class _Resp:
        def read(self):
            return _EXECUTE_2AXIS.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    ex = XMLAExecutor("http://x/olap", "DB")
    cells = ex.run_cells(
        "SELECT {[Measures].[Sales]} ON 0, [Geography].[Region].Members ON 1 FROM [Cube]"
    )
    assert cells == [
        Cell(members=("Q1", "East"), value=1.0),
        Cell(members=("Q2", "East"), value=2.0),
        Cell(members=("Q1", "West"), value=3.0),
        Cell(members=("Q2", "West"), value=4.0),
    ]


def test_run_cells_is_part_of_the_executor_protocol():
    assert hasattr(MdxExecutor, "run_cells")


def test_scalar_run_still_works_unchanged(monkeypatch):
    # back-compat: adding run_cells must not disturb the existing scalar path.
    ex = XMLAExecutor("http://x/olap", "DB")
    monkeypatch.setattr(ex._client, "execute", lambda mdx: 42.0)
    assert ex.run("SELECT [Measures].[X] ON 0 FROM [C]") == 42.0
