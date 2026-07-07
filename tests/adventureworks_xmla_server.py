"""A tiny in-process XMLA (SOAP) server serving an Adventure-Works-shaped cube.

Stands in for a real SSAS endpoint so the full mdx-mcp pipeline (introspect → produce →
execute → verify) can be validated over REAL HTTP + SOAP — not mocked. It answers:
  * Discover(MDSCHEMA_MEASURES|MDSCHEMA_DIMENSIONS|MDSCHEMA_HIERARCHIES) → schema rowsets
  * Execute(<MDX>) → the value of the measure named in the statement (single cell)

Not a real OLAP engine: Execute maps the measure NAME found in the MDX to a canned value,
which is exactly what a deterministic single-cell query needs for a self-consistency check.
"""
from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# The mini cube: measure name -> canned value.
CUBE = "Adventure Works"
MEASURES = {
    "Internet Sales Amount": 29358677.22,
    "Reseller Sales Amount": 80450596.98,
    "Order Count": 31465.0,
}
DIMENSIONS = ["Date", "Product", "Geography", "Measures"]
HIERARCHIES = ["[Date].[Calendar]", "[Product].[Category]", "[Geography].[Country]"]

_MDD = "urn:schemas-microsoft-com:xml-analysis:mddataset"
_ROW = "urn:schemas-microsoft-com:xml-analysis:rowset"


def _cell(value) -> str:
    v = "" if value is None else repr(float(value))
    return (f'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>'
            f'<ExecuteResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>'
            f'<root xmlns="{_MDD}"><CellData><Cell CellOrdinal="0"><Value>{v}</Value>'
            f'</Cell></CellData></root></return></ExecuteResponse></Body></Envelope>')


def _rowset(rows_xml: str) -> str:
    return (f'<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"><Body>'
            f'<DiscoverResponse xmlns="urn:schemas-microsoft-com:xml-analysis"><return>'
            f'<root xmlns="{_ROW}">{rows_xml}</root></return></DiscoverResponse></Body></Envelope>')


def _discover(request_type: str) -> str:
    if request_type == "MDSCHEMA_MEASURES":
        rows = "".join(f"<row><MEASURE_NAME>{m}</MEASURE_NAME></row>" for m in MEASURES)
    elif request_type == "MDSCHEMA_DIMENSIONS":
        rows = "".join(f"<row><DIMENSION_NAME>{d}</DIMENSION_NAME></row>" for d in DIMENSIONS)
    elif request_type == "MDSCHEMA_HIERARCHIES":
        rows = "".join(f"<row><HIERARCHY_UNIQUE_NAME>{h}</HIERARCHY_UNIQUE_NAME></row>"
                       for h in HIERARCHIES)
    else:
        rows = ""
    return _rowset(rows)


def _execute(mdx: str) -> str:
    for name, value in MEASURES.items():
        if name.lower() in mdx.lower():
            return _cell(value)
    return _cell(None)  # unknown measure → empty cell


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        if "<Discover" in body:
            rt = re.search(r"<RequestType>(.*?)</RequestType>", body, re.S)
            payload = _discover(rt.group(1).strip() if rt else "")
        elif "<Execute" in body:
            stmt = re.search(r"<Statement>(.*?)</Statement>", body, re.S)
            mdx = (stmt.group(1) if stmt else "").replace("&lt;", "<").replace("&gt;", ">") \
                .replace("&quot;", '"').replace("&amp;", "&")
            payload = _execute(mdx)
        else:
            payload = _cell(None)
        data = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", 'text/xml; charset="utf-8"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class XMLATestServer:
    """Context manager: starts the server on an ephemeral port; ``.endpoint`` is its URL."""

    def __init__(self) -> None:
        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._httpd.server_address[1]
        self.endpoint = f"http://127.0.0.1:{self.port}/xmla"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> "XMLATestServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
