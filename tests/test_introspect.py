"""Cube introspection → grounding block rendering."""
from mdx_mcp.introspect import render_skills


def test_render_skills_block():
    measures = [{"MEASURE_NAME": "Sales Amount"}, {"MEASURE_NAME": "Order Count"}]
    dims = [{"DIMENSION_NAME": "Date"}, {"DIMENSION_NAME": "Measures"}, {"DIMENSION_NAME": "Product"}]
    hiers = [{"HIERARCHY_UNIQUE_NAME": "[Date].[Calendar]"}]
    block = render_skills("Adventure Works", measures, dims, hiers)

    assert "Cube: [Adventure Works]" in block
    assert "[Measures].[Sales Amount]" in block and "[Measures].[Order Count]" in block
    # the 'Measures' pseudo-dimension is filtered out of Dimensions
    assert "- Date" in block and "- Product" in block
    assert "- Measures" not in block.split("Hierarchies")[0].split("Dimensions:")[1]
    assert "[Date].[Calendar]" in block
    assert "FROM [Adventure Works]" in block  # the closing MDX rule references the cube


def test_render_skills_handles_empty_sections():
    block = render_skills("C", [], [], [])
    assert "Cube: [C]" in block  # never crashes on an empty cube
