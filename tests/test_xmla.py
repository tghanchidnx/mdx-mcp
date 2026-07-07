"""XMLA SOAP parsers — cell value + rowset (no live server)."""
from xml.etree import ElementTree as ET

from mdx_mcp._xmla import parse_first_cell, parse_rowset

_EXECUTE = """<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>
 <ExecuteResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>
  <root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
   <CellData><Cell CellOrdinal="0"><Value>29358677.22</Value></Cell></CellData>
  </root>
 </return></ExecuteResponse>
</Body></Envelope>"""

_EXECUTE_EMPTY = """<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>
 <ExecuteResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>
  <root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
   <CellData><Cell CellOrdinal="0"><Value></Value></Cell></CellData>
  </root>
 </return></ExecuteResponse>
</Body></Envelope>"""

_DISCOVER = """<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>
 <DiscoverResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>
  <root xmlns="urn:schemas-microsoft-com:xml-analysis:rowset">
   <row><MEASURE_NAME>Sales Amount</MEASURE_NAME><MEASURE_UNIQUE_NAME>[Measures].[Sales Amount]</MEASURE_UNIQUE_NAME></row>
   <row><MEASURE_NAME>Order Count</MEASURE_NAME></row>
  </root>
 </return></DiscoverResponse>
</Body></Envelope>"""


def test_parse_first_cell_value():
    assert parse_first_cell(ET.fromstring(_EXECUTE)) == 29358677.22


def test_parse_first_cell_empty_is_none():
    assert parse_first_cell(ET.fromstring(_EXECUTE_EMPTY)) is None


def test_parse_rowset_rows():
    rows = parse_rowset(ET.fromstring(_DISCOVER))
    assert len(rows) == 2
    assert rows[0]["MEASURE_NAME"] == "Sales Amount"
    assert rows[0]["MEASURE_UNIQUE_NAME"] == "[Measures].[Sales Amount]"
    assert rows[1]["MEASURE_NAME"] == "Order Count"
