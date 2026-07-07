"""End-to-end integration over REAL HTTP + XMLA SOAP (local Adventure-Works cube).

Unlike the unit tests (which parse canned XML in-memory), these drive the actual XMLAClient
over the wire against a live local server: introspect, execute, the read-only guard, and the
full produce → execute → verify pipeline.
"""
import re

from mdx_mcp.executor import UnsafeMdxError, XMLAExecutor
from mdx_mcp.introspect import CubeIntrospector
from mdx_mcp.producer import MdxProducer
from mdx_mcp.verify import SelfConsistencyVerifier

from adventureworks_xmla_server import CUBE, MEASURES, XMLATestServer


def test_introspect_over_http():
    with XMLATestServer() as srv:
        skills = CubeIntrospector(srv.endpoint, "AdventureWorksDW", CUBE).skills()
    assert "Cube: [Adventure Works]" in skills
    assert "Internet Sales Amount" in skills and "Reseller Sales Amount" in skills
    assert "Date" in skills and "[Date].[Calendar]" in skills


def test_execute_over_http_returns_cell():
    with XMLATestServer() as srv:
        ex = XMLAExecutor(srv.endpoint, "AdventureWorksDW")
        val = ex.run("SELECT [Measures].[Internet Sales Amount] ON COLUMNS FROM [Adventure Works]")
    assert val == MEASURES["Internet Sales Amount"] == 29358677.22


def test_readonly_guard_blocks_write_against_live_server():
    with XMLATestServer() as srv:
        ex = XMLAExecutor(srv.endpoint, "AdventureWorksDW")
        # a batched write must never reach the wire
        try:
            ex.run("SELECT 1 ON 0 FROM [Adventure Works]; DROP CUBE [Adventure Works]")
            raised = False
        except UnsafeMdxError:
            raised = True
    assert raised


class _StubLLM:
    """Deterministic 'NL→MDX' for the local cube — maps the QUESTION to the right measure query.

    Reads only the ``Question:`` line (the grounding block lists every measure, so keying off
    the whole prompt would mispick — as a real ambiguous grounding would).
    """
    def complete(self, prompt: str) -> str:
        m = re.search(r"Question:\s*(.*)", prompt)
        q = (m.group(1) if m else prompt).lower()
        measure = "Internet Sales Amount"
        if "reseller" in q:
            measure = "Reseller Sales Amount"
        elif "order" in q or "count" in q:
            measure = "Order Count"
        return f"SELECT [Measures].[{measure}] ON COLUMNS FROM [{CUBE}]"


def test_full_ask_pipeline_over_http():
    with XMLATestServer() as srv:
        skills = CubeIntrospector(srv.endpoint, "AdventureWorksDW", CUBE).skills()
        candidates = MdxProducer(_StubLLM()).candidates("What were total internet sales?", skills, k=3)
        answer = SelfConsistencyVerifier().verify(candidates, XMLAExecutor(srv.endpoint, "AWDW"))
    assert answer.status == "answer"
    assert answer.value == 29358677.22
    assert answer.agreement == 1.0 and answer.executed == 3
    assert "Internet Sales Amount" in answer.mdx


def test_full_ask_reseller_path():
    with XMLATestServer() as srv:
        ans = SelfConsistencyVerifier().verify(
            MdxProducer(_StubLLM()).candidates("total reseller sales", "", k=3),
            XMLAExecutor(srv.endpoint, "AWDW"))
    assert ans.status == "answer" and ans.value == 80450596.98
