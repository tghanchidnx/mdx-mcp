"""Self-consistency verifier — answer / abstain / clarify."""
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


def test_single_candidate_below_threshold_when_alone_still_answers():
    # one executed candidate → agreement 1.0 → answers (the only evidence there is)
    ex = _Executor({"a": 5.0})
    ans = SelfConsistencyVerifier(min_agreement=0.6).verify(["a"], ex)
    assert ans.status == "answer" and ans.value == 5.0


def test_bad_candidate_does_not_vote(monkeypatch):
    class _Raiser:
        def run(self, mdx):
            if mdx == "bad":
                raise RuntimeError("boom")
            return 9.0
    ans = SelfConsistencyVerifier().verify(["bad", "ok1", "ok2"], _Raiser())
    assert ans.status == "answer" and ans.value == 9.0 and ans.executed == 2


def test_float_bucketing_treats_near_equal_as_equal():
    ex = _Executor({"a": 100.0, "b": 100.0000001})
    ans = SelfConsistencyVerifier(min_agreement=0.6).verify(["a", "b"], ex)
    assert ans.status == "answer"
