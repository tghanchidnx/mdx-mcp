# Architecture

`mdx-mcp` is a small pipeline of single-purpose units connected by three **seams** (typed
Protocols). The seams are the open-core contract: swap any implementation without touching
the engine — that's how a private, proprietary trust layer plugs in.

```
                 ┌─────────────┐
 question ─────▶ │ MdxProducer │──┐   candidates (list[str])
                 └─────────────┘  │
        cube_skills ▲             ▼
   ┌──────────────────┐   ┌───────────────────┐   ┌──────────────┐
   │ CubeIntrospector │   │     Verifier      │──▶│    Answer    │
   └──────────────────┘   │ (SelfConsistency) │   └──────────────┘
        │ XMLA Discover        │ runs each via
        ▼                      ▼
   ┌──────────────────────────────────┐
   │           MdxExecutor            │  (XMLAExecutor, read-only safe_mdx)
   └──────────────────────────────────┘
```

## Units
| Unit | Does | Depends on |
|------|------|-----------|
| `CubeIntrospector` | cube metadata → `cube_skills` grounding block | XMLA `Discover` |
| `MdxProducer` | NL + `cube_skills` → *k* candidate MDX | `LLMClient` |
| `MdxExecutor` | run read-only MDX → cell value | XMLA `Execute` |
| `Verifier` | candidates → verified `Answer` | `MdxExecutor` |
| `server` | wires the four MCP tools | all of the above |

## The three seams
- **`LLMClient`** — `complete(prompt) -> str`. Default `ClaudeClient`; bring any provider.
- **`MdxExecutor`** — `run(mdx) -> float | None`. Default `XMLAExecutor` (cross-platform);
  a Windows ADOMD backend is a drop-in.
- **`Verifier`** — `verify(candidates, executor) -> Answer`. Default `SelfConsistencyVerifier`
  (majority-agreement → answer, else abstain/clarify). A **calibrated trust gate**, cross-engine
  parity, or receipts belong *behind this seam*, in your private code — not in this repo.

## What this project deliberately does NOT do
No confidence **calibration**, no cross-engine (SQL↔MDX) parity, no audit receipts. Those are
higher-trust concerns intended to live behind the `Verifier` seam in a private layer. The OSS
goes exactly as deep as *"does the MDX run, and do the candidates agree?"*

## Read-only guarantee
`safe_mdx()` rejects anything that is not a `SELECT`/`WITH` query (and any write/DDL/admin
keyword) before execution. Every executor path calls it.
