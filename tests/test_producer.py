"""NL→MDX producer — fence stripping + diverse candidate generation."""
from mdx_mcp.producer import MdxProducer, extract_mdx


def test_extract_strips_fences_and_preamble():
    raw = "Here is the query:\n```mdx\nSELECT [Measures].[X] ON 0 FROM [C]\n```"
    assert extract_mdx(raw) == "SELECT [Measures].[X] ON 0 FROM [C]"


def test_extract_keeps_from_with():
    raw = "```\nWITH MEMBER [Measures].[Y] AS 1 SELECT [Measures].[Y] ON 0 FROM [C]\n```"
    assert extract_mdx(raw).startswith("WITH MEMBER")


def test_extract_prose_without_mdx_has_no_query():
    out = extract_mdx("I cannot answer that from this cube.")
    assert "select" not in out.lower()  # nothing that safe_mdx would accept as a query


class _LLM:
    """Records prompts; returns a deterministic MDX per call."""
    def __init__(self):
        self.prompts = []
    def complete(self, prompt):
        self.prompts.append(prompt)
        return f"```mdx\nSELECT [Measures].[M{len(self.prompts)}] ON 0 FROM [C]\n```"


def test_produces_k_candidates_with_diverse_prompts():
    llm = _LLM()
    cands = MdxProducer(llm).candidates("total sales", "Cube: [C]\nMeasures: [Measures].[Sales]", k=3)
    assert len(cands) == 3 and all(c.startswith("SELECT") for c in cands)
    # diverse lenses → the 3 prompts differ
    assert len(set(llm.prompts)) == 3
    # grounding block is included in the prompt
    assert "Cube: [C]" in llm.prompts[0]


def test_llm_error_skips_that_candidate():
    class _Flaky:
        def __init__(self):
            self.n = 0
        def complete(self, prompt):
            self.n += 1
            if self.n == 2:
                raise RuntimeError("rate limited")
            return "SELECT [Measures].[X] ON 0 FROM [C]"
    cands = MdxProducer(_Flaky()).candidates("q", "", k=3)
    assert len(cands) == 2  # the failed one is skipped, not fatal
