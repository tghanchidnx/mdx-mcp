# mdx-mcp

**An open-source, verified natural-language → MDX MCP server for OLAP cubes.**

Ask an OLAP/SSAS multidimensional cube questions in plain English and get back a **verified**
answer — the number, the MDX that produced it, and an honest *abstain/clarify* when the query
is ambiguous. Cross-platform (XMLA), provider-agnostic (Claude by default), and MCP-native.

```
question ──▶ introspect the cube ──▶ generate k candidate MDX ──▶ execute (read-only)
         ──▶ self-consistency verify ──▶ { status, value, mdx, agreement }
```

## Why it's different
- **Verified, not vibes.** It runs *k* diverse candidate queries and only answers when they
  agree; on divergence it **abstains or asks to clarify** instead of guessing a number.
- **Works on any cube.** Cube-schema **introspection** auto-grounds generation — no per-cube
  hand-authoring.
- **Read-only by construction.** Only `SELECT`/`WITH` MDX ever executes.
- **Open-core.** Three clean seams (`LLMClient`, `MdxExecutor`, `Verifier`) let you plug in a
  private trust layer without forking. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Install
```bash
pip install mdx-mcp[claude]     # engine + Claude reference provider
```
The XMLA executor and cube introspection use only the Python standard library.

## Configure (env)
```bash
export MDX_MCP_ENDPOINT="http://your-ssas-host/olap/msmdpump.dll"   # XMLA endpoint
export MDX_MCP_CATALOG="YourDatabase"
export MDX_MCP_CUBE="Your Cube"
export MDX_MCP_USER="user"           # optional (basic auth)
export MDX_MCP_PASSWORD_FILE="/run/secrets/olap_pw"   # or MDX_MCP_PASSWORD
export ANTHROPIC_API_KEY="sk-..."    # for the default Claude producer
```

## Run
```bash
mdx-mcp        # starts the MCP server (stdio)
```

## Tools
| Tool | Purpose |
|------|---------|
| `mdx_introspect` | the cube's grounding block (measures / dimensions / hierarchies) |
| `mdx_ask` | NL question → `{ status: answer\|abstain\|clarify, value, mdx, agreement }` |
| `mdx_run` | execute a provided MDX query (read-only) |
| `mdx_explain` | explain an MDX query in plain language |

Ships a **Cube-Analyst persona** ([`persona/`](persona/)) and **Claude skills**
([`skills/`](skills/)) that drive the flow.

## Bring your own provider / backend
Implement `LLMClient` (any model), `MdxExecutor` (e.g. a Windows ADOMD backend), or `Verifier`
(e.g. a calibrated trust gate) and inject it — the engine is unchanged.

## License
Apache-2.0. No vendor lock-in, no client data.
