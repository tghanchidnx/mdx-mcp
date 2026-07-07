"""Cube-schema introspection → a ``cube_skills`` grounding block.

Reads the cube's own metadata via XMLA ``Discover`` schema rowsets (measures, dimensions,
hierarchies) and renders a compact text block the producer uses to ground NL→MDX. This is
what makes the engine work on *any* cube with zero hand-authoring — no cube is hardcoded.
"""
from __future__ import annotations

from typing import Optional

from ._xmla import XMLAClient


class CubeIntrospector:
    """Introspect a cube's measures/dimensions/hierarchies into a grounding block."""

    def __init__(self, endpoint: str, catalog: str, cube: str, *, username: Optional[str] = None,
                 password: Optional[str] = None, timeout: float = 30.0) -> None:
        self.cube = cube
        self._client = XMLAClient(endpoint, catalog, username=username, password=password,
                                  timeout=timeout)

    def skills(self, max_per_section: int = 60) -> str:
        """Return a compact 'cube skills' text block describing this cube."""
        restr = {"CUBE_NAME": self.cube}
        measures = self._client.discover("MDSCHEMA_MEASURES", restr)
        dims = self._client.discover("MDSCHEMA_DIMENSIONS", restr)
        hiers = self._client.discover("MDSCHEMA_HIERARCHIES", restr)
        return render_skills(self.cube, measures, dims, hiers, max_per_section)


def render_skills(cube: str, measures: list[dict], dims: list[dict], hiers: list[dict],
                  cap: int = 60) -> str:
    """Render discovered rowsets into a compact grounding block (pure — unit-tested)."""
    lines = [f"Cube: [{cube}]", ""]

    def name(row: dict, *keys: str) -> Optional[str]:
        for k in keys:
            v = row.get(k)
            if v:
                return v
        return None

    ms = [name(r, "MEASURE_NAME", "MEASURE_UNIQUE_NAME") for r in measures]
    ms = [m for m in ms if m][:cap]
    if ms:
        lines.append("Measures (put ONE on COLUMNS):")
        lines += [f"  - [Measures].[{m}]" if not str(m).startswith("[") else f"  - {m}" for m in ms]
        lines.append("")

    ds = [name(r, "DIMENSION_NAME", "DIMENSION_UNIQUE_NAME") for r in dims]
    ds = [d for d in ds if d and str(d).lower() != "measures"][:cap]
    if ds:
        lines.append("Dimensions:")
        lines += [f"  - {d}" for d in ds]
        lines.append("")

    hs = [name(r, "HIERARCHY_UNIQUE_NAME", "HIERARCHY_NAME") for r in hiers]
    hs = [h for h in hs if h][:cap]
    if hs:
        lines.append("Hierarchies (use for slicing in WHERE / on ROWS):")
        lines += [f"  - {h}" for h in hs]
        lines.append("")

    lines.append("MDX rules: one measure on COLUMNS; slice context in WHERE; a bare query is "
                 "`SELECT [Measures].[X] ON COLUMNS FROM [" + cube + "]`.")
    return "\n".join(lines).strip()
