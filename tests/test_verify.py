"""Self-consistency verifier — answer / abstain / clarify."""
import pytest

from mdx_mcp._xmla import XMLAError
from mdx_mcp.verify import SelfConsistencyVerifier


class _Executor:
    """Maps a given MDX string to a canned value (None allowed)."""
    def __init__(self, table):
        self.table = table
    def run(self, mdx):
        return self.table[mdx]


def test_majority_agreement_answers():
    ex = _Executor({"a": 42.0, "b": 42.0, "c": 7.0})
    ans = SelfConsistencyVerifier(min_agreement=0.6).verify(["a", "b", "c"], ex)
    assert ans.status == "answer" and ans.value == 42.0
    assert ans.agreement == 2 / 3 and ans.executed == 3 and ans.mdx in ("a", "b")


def test_divergence_clarifies():
    ex = _Executor({"a": 1.0, "b": 2.0, "c": 3.0})
    ans = SelfConsistencyVerifier(min_agreement=0.6).verify(["a", "b", "c"], ex)
    assert ans.status == "clarify" and ans.value is None


def test_no_values_abstains():
    ex = _Executor({"a": None, "b": None})
    ans = SelfConsistencyVerifier().verify(["a", "b"], ex)
    assert ans.status == "abstain" and ans.executed == 0


def test_single_executed_candidate_abstains_no_corroboration():
    # one un-cross-checked value is NOT self-consistent → abstain (was a false "answer")
    ex = _Executor({"a": 5.0})
    ans = SelfConsistencyVerifier(min_executed=2).verify(["a"], ex)
    assert ans.status == "abstain" and ans.value is None and "corroborated" in ans.note


def test_expected_execution_error_does_not_vote_but_unexpected_propagates():
    class _Raiser:
        def run(self, mdx):
            if mdx == "bad":
                raise XMLAError("transport down")  # expected → skipped
            return 9.0
    ans = SelfConsistencyVerifier().verify(["bad", "ok1", "ok2"], _Raiser())
    assert ans.status == "answer" and ans.value == 9.0 and ans.executed == 2 and ans.errors == 1

    class _Bug:
        def run(self, mdx):
            raise AttributeError("real bug")  # unexpected → must NOT be swallowed
    with pytest.raises(AttributeError):
        SelfConsistencyVerifier().verify(["x", "y"], _Bug())


def test_all_candidates_error_reports_why():
    class _Down:
        def run(self, mdx):
            raise XMLAError("endpoint unreachable")
    ans = SelfConsistencyVerifier().verify(["a", "b", "c"], _Down())
    # a dead endpoint must NOT look like a genuinely ambiguous question
    assert ans.status == "abstain" and ans.errors == 3
    assert "endpoint unreachable" in ans.note


def test_tolerant_clustering_merges_near_and_splits_material_gaps():
    # near-equal across a power-of-10 boundary → same cluster → answer
    near = SelfConsistencyVerifier().verify(["a", "b"], _Executor({"a": 999999.4, "b": 999999.6}))
    assert near.status == "answer"
    # a material money gap ($21 on $12M) → distinct clusters → NOT false agreement
    gap = SelfConsistencyVerifier().verify(["a", "b"], _Executor({"a": 12345678.0, "b": 12345699.0}))
    assert gap.status == "clarify"
