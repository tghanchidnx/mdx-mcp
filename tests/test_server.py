"""MCP server surface — config, secrets, open-core injection, and guard wiring.

Covers the previously-untested server.py: without these, the read-only guarantee could be
disconnected from the tools with every other test still green.
"""
import asyncio

import pytest

from mdx_mcp.server import _conf, _password, build_server


def test_conf_raises_on_missing_env(monkeypatch):
    for v in ("MDX_MCP_ENDPOINT", "MDX_MCP_CATALOG", "MDX_MCP_CUBE"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(RuntimeError) as exc:
        _conf()
    assert "MDX_MCP_ENDPOINT" in str(exc.value)


def test_password_file_takes_precedence(monkeypatch, tmp_path):
    f = tmp_path / "pw"
    f.write_text("s3cret\n", encoding="utf-8")
    monkeypatch.setenv("MDX_MCP_PASSWORD_FILE", str(f))
    monkeypatch.setenv("MDX_MCP_PASSWORD", "ignored-env-value")
    assert _password() == "s3cret"


def test_password_file_missing_fails_not_silent(monkeypatch, tmp_path):
    # a configured-but-missing secret file must ERROR, not degrade to env/no-auth
    monkeypatch.setenv("MDX_MCP_PASSWORD_FILE", str(tmp_path / "nope"))
    monkeypatch.setenv("MDX_MCP_PASSWORD", "should-not-be-used")
    with pytest.raises(RuntimeError):
        _password()


def test_password_env_fallback_when_no_file(monkeypatch):
    monkeypatch.delenv("MDX_MCP_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("MDX_MCP_PASSWORD", "envpw")
    assert _password() == "envpw"


def test_build_server_accepts_injected_seams():
    # the open-core promise: seams are injectable through the PUBLIC entry point (no fork)
    class _V:  # a stand-in for e.g. a proprietary calibrated verifier
        def verify(self, candidates, executor):
            raise AssertionError("not called in this test")

    srv = build_server(verifier=_V(), executor_factory=lambda: object(),
                       llm=object(), producer=object())
    tools = asyncio.run(srv.list_tools())
    assert {t.name for t in tools} >= {"mdx_introspect", "mdx_ask", "mdx_run", "mdx_explain"}


def test_mdx_run_guard_is_wired_to_the_tool():
    # proves server.py isn't a no-op: a read reaches the (injected) executor with the guarded
    # MDX, and a WRITE is stopped by safe_mdx BEFORE the executor is ever touched.
    seen = []

    class _Ex:
        def run(self, mdx):
            seen.append(mdx)
            return 7.0

    srv = build_server(executor_factory=lambda: _Ex())
    asyncio.run(srv.call_tool("mdx_run", {"mdx": "SELECT [Measures].[X] ON 0 FROM [C]"}))
    assert seen == ["SELECT [Measures].[X] ON 0 FROM [C]"]  # read reached the executor

    seen.clear()
    try:
        asyncio.run(srv.call_tool("mdx_run", {"mdx": "SELECT 1 ON 0 FROM [C]; DROP CUBE [C]"}))
    except Exception:
        pass
    assert seen == []  # the write NEVER reached the executor — guard is wired
