"""Read-only guard — the security guarantee."""
import pytest

from mdx_mcp.executor import UnsafeMdxError, XMLAExecutor, safe_mdx


@pytest.mark.parametrize("mdx", [
    "SELECT [Measures].[Sales] ON COLUMNS FROM [Cube]",
    "  select [Measures].[X] on columns from [C] ",
    "WITH MEMBER [Measures].[Y] AS 1 SELECT [Measures].[Y] ON 0 FROM [C]",
    "(SELECT [Measures].[X] ON 0 FROM [C])",
])
def test_safe_mdx_allows_readonly(mdx):
    assert safe_mdx(mdx)  # returns non-empty, no raise


@pytest.mark.parametrize("mdx", [
    "DROP CUBE [C]",
    "CREATE MEMBER [C].[Measures].[bad] AS 1",
    "DELETE FROM [C]",
    "UPDATE CUBE [C] SET ...",
    "CALL SYSTEM.DISCOVER()",
    "",
    "   ",
    "EXECUTE something",
])
def test_safe_mdx_rejects_writes_and_empty(mdx):
    with pytest.raises(UnsafeMdxError):
        safe_mdx(mdx)


def test_safe_mdx_rejects_select_with_embedded_write():
    # a SELECT that smuggles a DROP must still be rejected
    with pytest.raises(UnsafeMdxError):
        safe_mdx("SELECT [Measures].[X] ON 0 FROM [C] ; DROP CUBE [C]")


def test_executor_guards_before_calling_backend(monkeypatch):
    ex = XMLAExecutor("http://x/olap", "DB")
    called = {"n": 0}

    def _boom(mdx):  # the XMLA client must never be hit for unsafe MDX
        called["n"] += 1
        return 1.0

    monkeypatch.setattr(ex._client, "execute", _boom)
    with pytest.raises(UnsafeMdxError):
        ex.run("DROP CUBE [C]")
    assert called["n"] == 0
