---
name: explain-mdx
description: Explain what an MDX query does in plain language. Use when the user wants to understand a generated or existing MDX query.
---

# explain-mdx

Teach what an MDX query means, using `mdx-mcp`.

## Steps
1. Take the MDX (from a prior `mdx_ask` result's `mdx`, or one the user pastes).
2. Call `mdx_explain(mdx=<the query>)`.
3. Relay the explanation, and connect it back to the business question: which **measure** is
   returned, what **slice/context** (`WHERE`) constrains it, and what single value results.
4. If the user wants to run it, use `mdx_run(mdx=<the query>)` (read-only).

## Guardrails
- Don't claim the query is "correct" — explain what it *does*; correctness is what `mdx_ask`'s
  verification is for.
