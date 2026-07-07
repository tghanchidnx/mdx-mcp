---
name: ask-the-cube
description: Answer a natural-language question against an OLAP cube with a VERIFIED MDX result. Use when the user asks for a number/metric from a cube connected via mdx-mcp.
---

# ask-the-cube

Turn a business question into a verified answer from the cube, using the `mdx-mcp` tools.

## Steps
1. **Ground first (once per cube).** If you don't already have the cube's schema in context,
   call `mdx_introspect` and keep the measures / dimensions / hierarchies for reference.
2. **Ask.** Call `mdx_ask(question=<the user's question>)`. It generates several candidate MDX
   queries, executes them read-only, and returns a self-consistency verdict.
3. **Act on `status` — honestly:**
   - `answer` → report the `value`, and show the `mdx` that produced it and the `agreement`.
   - `clarify` → the candidates disagreed → the question is ambiguous. Ask the user the ONE
     disambiguating question (which measure? which period/member? which entity?). Do not guess.
   - `abstain` → tell the user you couldn't get a trustworthy answer, and why. Never invent a number.
4. **Offer the query.** When you answer, optionally offer `mdx_explain(mdx)` so the user sees
   what the query did.

## Guardrails
- Use only measure/dimension/member names returned by `mdx_introspect` — never fabricate them.
- `agreement` is candidate agreement, not calibrated certainty — report it as such.
- Everything is read-only.
