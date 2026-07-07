"""The mdx-mcp MCP server — wires introspect → produce → execute → verify into four tools.

Configuration (env):
  MDX_MCP_ENDPOINT   XMLA/msmdpump URL of the OLAP server        (required)
  MDX_MCP_CATALOG    catalog / database name                     (required)
  MDX_MCP_CUBE       cube name                                   (required)
  MDX_MCP_USER       basic-auth user                             (optional)
  MDX_MCP_PASSWORD   basic-auth password (or *_PASSWORD_FILE)    (optional)
  MDX_MCP_K          candidates per question (default 3)
  ANTHROPIC_API_KEY  for the default Claude producer
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from .executor import XMLAExecutor, safe_mdx
from .introspect import CubeIntrospector
from .llm import ClaudeClient
from .producer import MdxProducer
from .verify import SelfConsistencyVerifier


def _password() -> Optional[str]:
    path = os.environ.get("MDX_MCP_PASSWORD_FILE")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return os.environ.get("MDX_MCP_PASSWORD")


def _conf() -> dict:
    ep, cat, cube = (os.environ.get("MDX_MCP_ENDPOINT"), os.environ.get("MDX_MCP_CATALOG"),
                     os.environ.get("MDX_MCP_CUBE"))
    missing = [n for n, v in (("MDX_MCP_ENDPOINT", ep), ("MDX_MCP_CATALOG", cat),
                              ("MDX_MCP_CUBE", cube)) if not v]
    if missing:
        raise RuntimeError(f"missing required config: {', '.join(missing)}")
    return {"endpoint": ep, "catalog": cat, "cube": cube,
            "username": os.environ.get("MDX_MCP_USER"), "password": _password()}


def _executor() -> XMLAExecutor:
    c = _conf()
    return XMLAExecutor(c["endpoint"], c["catalog"], username=c["username"], password=c["password"])


def _introspector() -> CubeIntrospector:
    c = _conf()
    return CubeIntrospector(c["endpoint"], c["catalog"], c["cube"],
                            username=c["username"], password=c["password"])


@lru_cache(maxsize=1)
def _cube_skills() -> str:
    return _introspector().skills()


def build_server():
    """Construct the FastMCP server with the four read-only tools."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("mdx-mcp")
    llm = ClaudeClient()
    producer = MdxProducer(llm)
    verifier = SelfConsistencyVerifier()

    @mcp.tool()
    def mdx_introspect() -> str:
        """Return the cube's 'skills' block: measures, dimensions, hierarchies for grounding."""
        return _cube_skills()

    @mcp.tool()
    def mdx_ask(question: str, k: int = 0) -> dict:
        """Answer a natural-language question with a verified MDX result.

        Introspects the cube, generates k candidate MDX queries, executes them read-only,
        and returns the self-consistency verdict: {status: answer|abstain|clarify, value, mdx,
        agreement, ...}. Never guesses a number when candidates disagree.
        """
        k = k or int(os.environ.get("MDX_MCP_K", "3"))
        candidates = producer.candidates(question, _cube_skills(), k=k)
        answer = verifier.verify(candidates, _executor())
        return answer.to_dict()

    @mcp.tool()
    def mdx_run(mdx: str) -> dict:
        """Execute a provided MDX query (read-only; SELECT/WITH only) and return the cell value."""
        value = _executor().run(safe_mdx(mdx))
        return {"mdx": safe_mdx(mdx), "value": value}

    @mcp.tool()
    def mdx_explain(mdx: str) -> str:
        """Explain a given MDX query in plain language (what it measures, slices, and returns)."""
        prompt = ("Explain this MDX query in 3-4 plain sentences — the measure, the slice/context, "
                  "and what single value it returns:\n\n" + mdx)
        return llm.complete(prompt)

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
