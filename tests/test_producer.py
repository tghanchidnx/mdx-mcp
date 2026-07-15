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


def test_extract_ignores_prose_select_keeps_real_statement():
    # a preamble containing the word "select"/"with" must NOT be prepended to the MDX
    raw = "To answer this, I will select the Sales measure:\n\nSELECT [Measures].[Sales] ON 0 FROM [C]"
    assert extract_mdx(raw) == "SELECT [Measures].[Sales] ON 0 FROM [C]"
    raw2 = "Sure, here is the query with the total:\n```mdx\nSELECT [Measures].[X] ON 0 FROM [C]\n```"
    assert extract_mdx(raw2) == "SELECT [Measures].[X] ON 0 FROM [C]"


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


# ---------------------------------------------------------------------------
# shape param (PR #2): cell (default, back-compat) / cellset / auto
# ---------------------------------------------------------------------------

class _CapturingLLM:
    """Records every prompt it is asked to complete; always returns valid MDX."""
    def __init__(self):
        self.prompts = []
    def complete(self, prompt):
        self.prompts.append(prompt)
        return "SELECT [Measures].[X] ON 0 FROM [C]"


# Regression pin: the EXACT prompt text produced by today's (pre-shape) _prompt(),
# captured verbatim from mdx_mcp/producer.py before this change (dash is —, not '-').
_CELL_PROMPT_PIN = (
    "You are querying this OLAP cube:\n"
    "Cube: [Mock Ops Cube]\nMeasures: [Measures].[Operating Cost]"
    "\n\nQuestion: operating cost by area"
    "\n\nWrite MDX using the most direct reading of the question."
    "\n\nReply with ONLY the MDX — a single SELECT that yields ONE cell "
    "(one measure on COLUMNS, the relevant context in WHERE). No prose, no code fences."
)

_SKILLS = "Cube: [Mock Ops Cube]\nMeasures: [Measures].[Operating Cost]"


def test_shape_defaults_to_cell_and_is_byte_identical_to_todays_prompt():
    llm = _CapturingLLM()
    MdxProducer(llm).candidates("operating cost by area", _SKILLS, k=1)
    assert llm.prompts[0] == _CELL_PROMPT_PIN


def test_shape_cell_explicit_matches_default_byte_identical():
    llm = _CapturingLLM()
    MdxProducer(llm).candidates("operating cost by area", _SKILLS, k=1, shape="cell")
    assert llm.prompts[0] == _CELL_PROMPT_PIN


def test_shape_cellset_asks_for_rows_not_a_single_cell():
    llm = _CapturingLLM()
    MdxProducer(llm).candidates("top 5 wells by production", "", k=1, shape="cellset")
    prompt = llm.prompts[0]
    assert "ONE cell" not in prompt
    assert "ROWS" in prompt
    assert "TOPCOUNT" in prompt or "MEMBERS" in prompt
    assert "No prose, no code fences." in prompt  # discipline preserved


def test_shape_cellset_still_diversifies_lenses():
    llm = _CapturingLLM()
    MdxProducer(llm).candidates("top wells by production", "", k=3, shape="cellset")
    assert len(set(llm.prompts)) == 3


def test_shape_auto_constrains_neither_scalar_nor_cellset():
    llm = _CapturingLLM()
    MdxProducer(llm).candidates("operating cost by area", "", k=1, shape="auto")
    prompt = llm.prompts[0]
    # must NOT force a single cell the way shape="cell" does...
    assert "a single SELECT that yields ONE cell" not in prompt
    # ...but must still describe both the scalar and the rows/ranking option
    assert "ROWS" in prompt
    assert "one number" in prompt or "single" in prompt.lower()
    assert "No prose, no code fences." in prompt


def test_unknown_shape_raises_clear_error():
    llm = _CapturingLLM()
    try:
        MdxProducer(llm).candidates("q", "", k=1, shape="bogus")
        assert False, "expected ValueError for unknown shape"
    except ValueError as exc:
        assert "bogus" in str(exc)
    assert llm.prompts == []  # must fail BEFORE calling the LLM, not swallow via the retry loop


def test_server_call_site_signature_is_unaffected():
    """server.py calls producer.candidates(question, _cube_skills(), k=k) — no shape kwarg.
    Guard that this positional/keyword call shape still works and defaults to 'cell'."""
    llm = _CapturingLLM()
    out = MdxProducer(llm).candidates("total sales", "Cube: [C]", k=2)
    assert len(out) == 2
