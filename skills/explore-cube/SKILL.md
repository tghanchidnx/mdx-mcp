---
name: explore-cube
description: Explore what an OLAP cube contains (measures, dimensions, hierarchies) before querying it. Use when the user asks what's in the cube or you need to ground before asking questions.
---

# explore-cube

Help the user understand a cube's structure via `mdx-mcp`.

## Steps
1. Call `mdx_introspect` to get the cube's grounding block.
2. Summarize for the user, grouped:
   - **Measures** — the numbers they can ask for (one goes on COLUMNS).
   - **Dimensions / Hierarchies** — the ways to slice (period, entity, geography, …).
3. Suggest 2–3 concrete questions they could ask next (phrased in business terms), each of
   which maps cleanly onto a measure + a slice you just listed.
4. Hand off to `ask-the-cube` when they pick one.

## Guardrails
- Only describe what `mdx_introspect` actually returned — don't infer measures that aren't there.
