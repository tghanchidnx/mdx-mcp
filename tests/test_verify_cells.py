"""Self-consistency verifier over CELLSETS — multi-cell answers (rankings/breakdowns).

Extends ``SelfConsistencyVerifier`` to cluster whole cellsets (ordered, positional,
tolerant-equal), not just scalars. A scalar is unified as a 1-row cellset, so the existing
scalar tests in ``tests/test_verify.py`` keep passing unchanged.
"""
from mdx_mcp._xmla import XMLAError
from mdx_mcp.executor import Cell
from mdx_mcp.verify import SelfConsistencyVerifier


class _CellsExecutor:
    """Maps a given MDX string to a canned cellset via ``run_cells`` (no ``run``)."""
    def __init__(self, table):
        self.table = table

    def run_cells(self, mdx):
        v = self.table[mdx]
        if isinstance(v, Exception):
            raise v
        return v


class _ScalarExecutor:
    """Only ``run`` — no ``run_cells`` — the pre-Task-1 shape of a candidate executor."""
    def __init__(self, table):
        self.table = table

    def run(self, mdx):
        return self.table[mdx]


_RANKING = [Cell(members=("Alice",), value=100.0), Cell(members=("Bob",), value=90.0)]


def test_row_identical_cellsets_answer_with_full_agreement():
    ex = _CellsExecutor({"a": _RANKING, "b": list(_RANKING), "c": list(_RANKING)})
    ans = SelfConsistencyVerifier().verify(["a", "b", "c"], ex)
    assert ans.status == "answer"
    assert ans.agreement == 1.0
    assert ans.executed == 3
    assert ans.cells == _RANKING
    # scalar back-compat: Answer.value mirrors the modal cellset's FIRST cell value
    assert ans.value == 100.0


def test_divergent_but_numerically_close_cellset_is_not_clustered_as_agreement():
    # Same values as a SET, but at different positions/members — a value-only clusterer
    # would wrongly call this agreement. Positional (members, value) equality must not.
    a = [Cell(members=("Alice",), value=100.0), Cell(members=("Bob",), value=90.0)]
    b = [Cell(members=("Bob",), value=100.0), Cell(members=("Alice",), value=90.0)]
    ex = _CellsExecutor({"a": a, "b": b})
    ans = SelfConsistencyVerifier(min_agreement=0.6).verify(["a", "b"], ex)
    assert ans.status in ("clarify", "abstain")
    assert ans.status != "answer"


def test_all_candidates_error_reports_why_unchanged():
    ex = _CellsExecutor({
        "a": XMLAError("endpoint unreachable"),
        "b": XMLAError("endpoint unreachable"),
        "c": XMLAError("endpoint unreachable"),
    })
    ans = SelfConsistencyVerifier().verify(["a", "b", "c"], ex)
    assert ans.status == "abstain"
    assert ans.executed == 0 and ans.errors == 3
    assert "endpoint unreachable" in ans.note


def test_scalar_still_works_via_1row_cellset_unification():
    # No run_cells at all — the verifier must fall back to wrapping ``run`` as a 1-row cellset.
    ex = _ScalarExecutor({"a": 42.0, "b": 42.0, "c": 7.0})
    ans = SelfConsistencyVerifier(min_agreement=0.6).verify(["a", "b", "c"], ex)
    assert ans.status == "answer" and ans.value == 42.0
    assert ans.agreement == 2 / 3 and ans.executed == 3
    assert ans.cells == [Cell(members=(), value=42.0)]
