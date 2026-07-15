"""mdx-mcp — an open-source, verified NL→MDX MCP server for OLAP cubes.

Open-core: this package is the standalone engine (introspect → produce → execute → verify)
exposed over MCP. The three seams — :class:`LLMClient`, :class:`MdxExecutor`, :class:`Verifier`
— let a private trust layer plug in without forking. Apache-2.0.
"""
from .executor import Cell, MdxExecutor, UnsafeMdxError, XMLAExecutor, safe_mdx
from .introspect import CubeIntrospector, render_skills
from .llm import ClaudeClient, LLMClient
from .producer import MdxProducer, extract_mdx
from .verify import Answer, SelfConsistencyVerifier, Verifier

__version__ = "0.1.0"

__all__ = [
    "MdxExecutor", "XMLAExecutor", "Cell", "safe_mdx", "UnsafeMdxError",
    "CubeIntrospector", "render_skills",
    "LLMClient", "ClaudeClient",
    "MdxProducer", "extract_mdx",
    "Verifier", "SelfConsistencyVerifier", "Answer",
    "__version__",
]
