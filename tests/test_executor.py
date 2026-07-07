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


@pytest.mark.parametrize("mdx", [
    # multi-statement batching is the SCOPE/write-injection vector — reject even if both look read
    "SELECT 1 ON 0 FROM [C]; SCOPE([Measures].[X]); THIS = 100; END SCOPE",
    "SELECT [Measures].[X] ON 0 FROM [C]; SELECT [Measures].[Y] ON 0 FROM [C]",
    "SELECT 1 ON 0 FROM [C] ; SET [Measures].[X] = 5",
])
def test_safe_mdx_rejects_statement_batching(mdx):
    with pytest.raises(UnsafeMdxError):
        safe_mdx(mdx)


@pytest.mark.parametrize("mdx", [
    "SELECT [Measures].[Drop-off Rate] ON 0 FROM [C]",
    "SELECT [Measures].[Update Log] ON 0 FROM [C]",
    "SELECT [Measures].[Create Date] ON 0 FROM [C]",
    "SELECT [Measures].[Deleted Flag] ON 0 FROM [C]",
    "WITH MEMBER [Measures].[Insert Rate] AS 1 SELECT [Measures].[Insert Rate] ON 0 FROM [C]",
])
def test_safe_mdx_allows_member_names_containing_keywords(mdx):
    # false-positive fix: a keyword INSIDE a bracketed name must not block a read-only query
    assert safe_mdx(mdx)


def test_safe_mdx_masks_string_literals_with_semicolons():
    # a ';' inside a string literal is not statement batching
    assert safe_mdx("WITH MEMBER [Measures].[M] AS 'a;b' SELECT [Measures].[M] ON 0 FROM [C]")


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
