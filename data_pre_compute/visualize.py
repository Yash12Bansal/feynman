"""Visualize a concept graph as an interactive HTML network diagram using D3.js.

Usage:
    python visualize.py <input_file> [--output <output.html>]

Input can be:
    - .json file (concept graph JSON)
    - .md file (will look for matching .json in same directory)

Examples:
    python visualize.py output/Chapter_4_graph.json
    python visualize.py output/Chapter_4_graph.json --output my_graph.html
    python visualize.py output/Chapter_4_graph_outline.md
"""

import argparse
import json
import sys
from pathlib import Path


EDGE_COLORS = {
    "parent_child": "#94a3b8",
    "prerequisite": "#ef4444",
    "related": "#3b82f6",
    "leads_to": "#22c55e",
    "example_of": "#f59e0b",
}

LEVEL_COLORS = [
    "#1e293b",
    "#2563eb",
    "#059669",
    "#d97706",
    "#dc2626",
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; overflow: hidden; }}
  svg {{ display: block; }}
  .node-box {{ cursor: pointer; transition: filter 0.2s; }}
  .node-box:hover {{ filter: brightness(1.2); }}
  .node-label {{ pointer-events: none; fill: white; font-weight: 600; }}
  .edge-label {{ font-size: 10px; fill: #64748b; pointer-events: none; }}
  .link {{ fill: none; }}
  #tooltip {{
    position: fixed; display: none; background: white; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 14px 18px; max-width: 420px; font-size: 13px;
    line-height: 1.5; box-shadow: 0 4px 20px rgba(0,0,0,0.12); z-index: 1000;
    color: #334155;
  }}
  #tooltip h3 {{ margin: 0 0 8px; color: #1e293b; font-size: 15px; }}
  #tooltip .meta {{ font-size: 11px; color: #94a3b8; margin-bottom: 6px; }}
  #legend {{
    position: fixed; top: 14px; left: 14px; background: white; padding: 16px 20px;
    border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); z-index: 999;
    font-size: 12px; color: #475569;
  }}
  #legend h3 {{ font-size: 15px; color: #1e293b; margin-bottom: 10px; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
  .legend-line {{ width: 28px; height: 3px; border-radius: 2px; }}
  .legend-dash {{ width: 28px; height: 0; border-top: 3px dashed; }}
</style>
</head>
<body>

<div id="legend">
  <h3>{title}</h3>
  <div style="margin-bottom:6px; font-weight:600;">Edges:</div>
  <div class="legend-item"><div class="legend-line" style="background:#94a3b8;"></div> Parent / Child</div>
  <div class="legend-item"><div class="legend-line" style="background:#ef4444;"></div> Prerequisite</div>
  <div class="legend-item"><div class="legend-dash" style="border-color:#3b82f6;"></div> Related</div>
  <div class="legend-item"><div class="legend-line" style="background:#22c55e;"></div> Leads To</div>
  <div class="legend-item"><div class="legend-dash" style="border-color:#f59e0b;"></div> Example Of</div>
  <div style="margin-top:10px; color:#94a3b8;">Hover nodes for details. Drag to rearrange. Scroll to zoom.</div>
</div>

<div id="tooltip"></div>
<svg id="graph"></svg>

<script>
const graphData = {graph_json};

const width = window.innerWidth;
const height = window.innerHeight;

const svg = d3.select("#graph")
  .attr("width", width)
  .attr("height", height);

const g = svg.append("g");

// Zoom
const zoom = d3.zoom()
  .scaleExtent([0.2, 4])
  .on("zoom", (e) => g.attr("transform", e.transform));
svg.call(zoom);

// Prepare data
const nodes = Object.values(graphData.nodes).map(n => ({{
  id: n.node_id,
  label: n.topic_name,
  summary: n.summary,
  level: n.level,
  order: n.order,
  pageStart: n.page_start,
  pageEnd: n.page_end,
}}));

const links = graphData.edges.map(e => ({{
  source: e.source_id,
  target: e.target_id,
  relation: e.relation,
  label: e.label || e.relation.replace("_", " "),
}}));

const edgeColors = {edge_colors_json};
const levelColors = {level_colors_json};

// Arrow markers for each edge type
Object.entries(edgeColors).forEach(([rel, color]) => {{
  svg.append("defs").append("marker")
    .attr("id", "arrow-" + rel)
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 20)
    .attr("refY", 0)
    .attr("markerWidth", 8)
    .attr("markerHeight", 8)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M0,-5L10,0L0,5")
    .attr("fill", color);
}});

// Force simulation
const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(180))
  .force("charge", d3.forceManyBody().strength(-800))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("y", d3.forceY().y(d => 100 + d.level * 180).strength(0.3))
  .force("x", d3.forceX().x(width / 2).strength(0.05))
  .force("collision", d3.forceCollide().radius(80));

// Draw edges
const link = g.append("g").selectAll("path")
  .data(links).enter().append("path")
  .attr("class", "link")
  .attr("stroke", d => edgeColors[d.relation] || "#94a3b8")
  .attr("stroke-width", d => d.relation === "parent_child" ? 2.5 : 2)
  .attr("stroke-dasharray", d => (d.relation === "related" || d.relation === "example_of") ? "6,4" : "none")
  .attr("marker-end", d => "url(#arrow-" + d.relation + ")");

// Edge labels
const edgeLabel = g.append("g").selectAll("text")
  .data(links.filter(d => d.relation !== "parent_child"))
  .enter().append("text")
  .attr("class", "edge-label")
  .attr("text-anchor", "middle")
  .text(d => d.label.length > 30 ? d.label.slice(0, 30) + "..." : d.label);

// Draw nodes
const node = g.append("g").selectAll("g")
  .data(nodes).enter().append("g")
  .attr("class", "node-box")
  .call(d3.drag()
    .on("start", dragStart)
    .on("drag", dragging)
    .on("end", dragEnd));

// Node rectangles
node.append("rect")
  .attr("rx", 8).attr("ry", 8)
  .attr("fill", d => levelColors[Math.min(d.level, levelColors.length - 1)])
  .attr("stroke", d => d3.color(levelColors[Math.min(d.level, levelColors.length - 1)]).brighter(0.5))
  .attr("stroke-width", 1.5);

// Node text
node.append("text")
  .attr("class", "node-label")
  .attr("text-anchor", "middle")
  .attr("dy", "0.35em")
  .attr("font-size", d => Math.max(13 - d.level, 10))
  .text(d => d.label.length > 25 ? d.label.slice(0, 23) + "..." : d.label);

// Size rects to fit text
node.each(function() {{
  const text = d3.select(this).select("text");
  const bbox = text.node().getBBox();
  d3.select(this).select("rect")
    .attr("x", bbox.x - 14)
    .attr("y", bbox.y - 10)
    .attr("width", bbox.width + 28)
    .attr("height", bbox.height + 20);
}});

// Tooltip
const tooltip = d3.select("#tooltip");

node.on("mouseover", (event, d) => {{
  tooltip.style("display", "block")
    .html(`<h3>${{d.label}}</h3>
           <div class="meta">Level ${{d.level}} &middot; Pages ${{d.pageStart}}-${{d.pageEnd}}</div>
           ${{d.summary}}`);
}})
.on("mousemove", (event) => {{
  let x = event.clientX + 16;
  let y = event.clientY + 16;
  if (x + 420 > width) x = event.clientX - 436;
  if (y + 300 > height) y = event.clientY - 200;
  tooltip.style("left", x + "px").style("top", y + "px");
}})
.on("mouseout", () => tooltip.style("display", "none"));

// Tick
simulation.on("tick", () => {{
  link.attr("d", d => {{
    const dx = d.target.x - d.source.x;
    const dy = d.target.y - d.source.y;
    return `M${{d.source.x}},${{d.source.y}} L${{d.target.x}},${{d.target.y}}`;
  }});

  edgeLabel
    .attr("x", d => (d.source.x + d.target.x) / 2)
    .attr("y", d => (d.source.y + d.target.y) / 2 - 8);

  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

// Drag handlers
function dragStart(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragging(event, d) {{
  d.fx = event.x; d.fy = event.y;
}}
function dragEnd(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}}

// Center initially
svg.call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(0.9));
</script>
</body>
</html>"""


def load_graph(input_path: Path) -> dict:
    """Load graph data from JSON or find JSON from MD path."""
    if input_path.suffix == ".md":
        json_path = input_path.with_name(
            input_path.name.replace("_graph_outline.md", "_graph.json")
        )
        if not json_path.exists():
            json_path = input_path.with_suffix(".json")
        if not json_path.exists():
            print(f"Could not find matching JSON file for: {input_path}")
            sys.exit(1)
        input_path = json_path
        print(f"Using JSON file: {input_path}")

    if input_path.suffix != ".json":
        print(f"Unsupported file type: {input_path.suffix}. Use .json or .md")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        return json.load(f)


def build_visualization(graph_data: dict, output_path: Path):
    """Build an interactive D3.js force-directed graph."""
    title = graph_data.get("chapter_title", "Concept Graph")

    html = HTML_TEMPLATE.format(
        title=title,
        graph_json=json.dumps(graph_data, ensure_ascii=False),
        edge_colors_json=json.dumps(EDGE_COLORS),
        level_colors_json=json.dumps(LEVEL_COLORS),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    nodes = graph_data.get("nodes", {})
    edges = graph_data.get("edges", [])
    print(f"Saved visualization: {output_path}")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Edges: {len(edges)}")


def main():
    parser = argparse.ArgumentParser(description="Visualize a concept graph")
    parser.add_argument("input", help="Path to graph JSON or outline MD file")
    parser.add_argument("--output", "-o", default=None, help="Output HTML path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    graph_data = load_graph(input_path)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(
            input_path.stem.replace("_graph", "") + "_viz.html"
        )

    build_visualization(graph_data, output_path)
    print(f"\nOpen in browser: file://{output_path.resolve()}")


if __name__ == "__main__":
    main()
