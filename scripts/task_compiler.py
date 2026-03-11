"""
Task Compiler for Looker Studio Automation

Compiles dashboard_config.json into a single concise task string
using the Looker Studio UI Playbook for exact chart type names.
"""

import json
import os
import re

# Deterministic color name → hex mapping
COLOR_MAP = {
    "red": "#EA4335",
    "blue": "#4285F4",
    "green": "#34A853",
    "yellow": "#FBBC04",
    "orange": "#FF6D00",
    "purple": "#7B1FA2",
    "teal": "#00897B",
    "pink": "#E91E63",
    "grey": "#9E9E9E",
    "gray": "#9E9E9E",
    "black": "#212121",
    "white": "#FFFFFF",
    "navy": "#1A237E",
    "brown": "#6D4C41",
}

# Standard layout keyword → vision_click description (relative to previous chart)
LAYOUT_POSITION_MAP = {
    "right": "flush to the top and right of the viz's outer boundary box",
    "left-right": "flush to the top and right of the viz's outer boundary box",
    "below": "flush to the bottom of the viz's outer boundary box",
    "top-bottom": "flush to the bottom of the viz's outer boundary box",
    "below-left": "flush to the bottom-left of the viz's outer boundary box",
    "below-right": "flush to the bottom-right of the viz's outer boundary box",
}


def resolve_color(value: str) -> str:
    """Resolve a color name to hex. Returns value unchanged if already hex or unknown."""
    if not value:
        return value
    if re.match(r'^#[0-9A-Fa-f]{3,6}$', value.strip()):
        return value.strip()
    return COLOR_MAP.get(value.strip().lower(), value.strip())


def translate_config(config: dict) -> dict:
    """Pre-process config: resolve color names to hex in all visualizations."""
    for viz in config.get("visualizations", []):
        sc = viz.get("special_configurations", {})
        if sc.get("chart_color"):
            sc["chart_color"] = resolve_color(sc["chart_color"])
        if sc.get("background_color"):
            sc["background_color"] = resolve_color(sc["background_color"])
    return config


def load_playbook(playbook_path: str = None) -> dict:
    if playbook_path is None:
        playbook_path = os.path.join(os.path.dirname(__file__), "looker_studio_playbook.json")
    with open(playbook_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_chart_type(raw_type: str, playbook: dict) -> str:
    """Resolve user-provided chart type to exact Looker Studio UI label."""
    raw_lower = raw_type.strip().lower()
    aliases = playbook.get("chart_type_aliases", {})
    if raw_lower in aliases:
        return aliases[raw_lower]
    labels = playbook.get("chart_type_labels", {})
    if raw_lower in labels:
        return labels[raw_lower]
    for label in labels.values():
        if label.lower() == raw_lower:
            return label
    return raw_type.strip()


def expand_procedure(procedure_name: str, playbook: dict, params: dict = None) -> list[str]:
    """Expand a playbook procedure into steps with parameters filled in."""
    procedures = playbook.get("procedures", {})
    if procedure_name not in procedures:
        return []
    steps = list(procedures[procedure_name]["steps"])
    if params:
        steps = [step.format(**params) for step in steps]
    return steps


def compile_config(config_path: str, playbook_path: str = None) -> dict:
    """Compile a dashboard config into a single task string."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    config = translate_config(config)
    playbook = load_playbook(playbook_path)
    steps = []
    step_num = [0]

    def add(text: str):
        step_num[0] += 1
        steps.append(f"{step_num[0]}. {text}")

    def add_procedure(name: str, params: dict = None):
        for s in expand_procedure(name, playbook, params):
            add(s)

    # === Init & Connect ===
    ds = config.get("data_source", {})
    add_procedure("create_blank_report")
    add_procedure("connect_bigquery", {
        "project_id": ds.get("project_id", ""),
        "dataset": ds.get("dataset", ""),
        "table": ds.get("table_name", ""),
    })

    # === Charts ===
    visualizations = config.get("visualizations", [])
    layout_instructions = config.get("layout_instructions", [])

    for i, viz in enumerate(visualizations):
        chart_type_raw = viz.get("chart_type", "").strip()
        layout_desc = layout_instructions[i] if i < len(layout_instructions) else "an empty area on the canvas"

        # === Special element types (non-chart) ===
        if chart_type_raw.lower() in ("text", "text_box"):
            add("Scroll canvas to top")
            text_content = viz.get("title", "") or viz.get("text_content", "")
            add_procedure("add_text_element", {
                "position_description": layout_desc,
                "text_content": text_content,
            })
            # Text elements support sizing
            width = viz.get("width")
            height = viz.get("height")
            if width and height:
                add_procedure("set_chart_size", {"width": str(width), "height": str(height)})
            continue

        if chart_type_raw.lower() in ("date_range_control", "date_range", "date_control"):
            add("Scroll canvas to top")
            add_procedure("add_date_range_control", {
                "position_description": layout_desc,
            })
            # Date range controls support sizing
            width = viz.get("width")
            height = viz.get("height")
            if width and height:
                add_procedure("set_chart_size", {"width": str(width), "height": str(height)})
            continue

        # === Standard chart types ===
        if not chart_type_raw:
            title_lower = viz.get("title", "").lower()
            if "pie" in title_lower: chart_type_raw = "pie"
            elif "line" in title_lower or "trend" in title_lower: chart_type_raw = "time_series"
            elif "scorecard" in title_lower or "kpi" in title_lower: chart_type_raw = "scorecard"
            elif "table" in title_lower: chart_type_raw = "table"
            elif "geo" in title_lower or "map" in title_lower: chart_type_raw = "geo"
            else: chart_type_raw = "bar"

        chart_type_label = resolve_chart_type(chart_type_raw, playbook)

        # Add & place
        add("Scroll canvas to top")
        add_procedure("add_and_place_chart", {
            "chart_type": chart_type_label,
            "position_description": layout_desc,
        })

        # Chart sizing
        width = viz.get("width")
        height = viz.get("height")
        if width and height:
            add_procedure("set_chart_size", {"width": str(width), "height": str(height)})

        # Dimensions
        dimensions = viz.get("dimensions", [])
        if dimensions:
            add_procedure("set_dimension", {"dimension_name": dimensions[0]})
            for dim in dimensions[1:]:
                add_procedure("add_dimension", {"dimension_name": dim})

        # Metrics
        metrics = viz.get("metrics", [])
        if metrics:
            add_procedure("set_metric", {"metric_name": metrics[0]})
            for met in metrics[1:]:
                add_procedure("add_metric", {"metric_name": met})

        # Sorting
        sort_by = viz.get("sort_by")
        sort_order = viz.get("sort_order", "Descending")
        if sort_by:
            add_procedure("set_sort", {"sort_field": sort_by, "sort_order": sort_order})

        # Row limit
        row_limit = viz.get("row_limit")
        if row_limit:
            add_procedure("set_row_limit", {"row_limit": str(row_limit)})

        # Setup-level configurations (before switching to Style tab)
        sc = viz.get("special_configurations", {})
        if sc.get("compact_numbers"):
            for s in expand_procedure("style_toggle_compact_numbers", playbook):
                add(s)

        # Style tab configurations
        title = viz.get("title", "")
        style_parts = []

        if title:
            style_parts.extend(expand_procedure("style_set_title", playbook, {"title_text": title}))
        if sc.get("chart_color") and sc["chart_color"].lower() not in ("default", "none", ""):
            style_parts.extend(expand_procedure("style_set_color", playbook, {"color_value": sc["chart_color"]}))
        if sc.get("font_size"):
            style_parts.extend(expand_procedure("style_set_font_size", playbook, {"font_size": sc["font_size"]}))
        if sc.get("show_x_axis_title"):
            style_parts.extend(expand_procedure("style_toggle_x_axis_title", playbook))
        if sc.get("show_y_axis_title"):
            style_parts.extend(expand_procedure("style_toggle_y_axis_title", playbook))
        if sc.get("add_shadow"):
            style_parts.extend(expand_procedure("style_toggle_shadow", playbook))
        if sc.get("legend_position"):
            style_parts.extend(expand_procedure("style_set_legend_position", playbook, {"position": sc["legend_position"]}))
        if sc.get("show_data_labels"):
            style_parts.extend(expand_procedure("style_toggle_data_labels", playbook))
        if sc.get("background_color"):
            style_parts.extend(expand_procedure("style_set_background_color", playbook, {"color_value": sc["background_color"]}))
        if sc.get("other"):
            style_parts.extend(expand_procedure("others", playbook, {"others": sc["others"]}))

        if style_parts:
            add("Switch to 'Style' tab")
            for sp in style_parts:
                add(sp)

    task_string = "\n".join(steps)

    return {
        "task_string": task_string,
        "vertex_ai_project_id": config.get("vertex_ai_project_id", ""),
        "user_data_dir": config.get("user_data_dir", ""),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compile dashboard config into task")
    parser.add_argument("--config", required=True, help="Path to dashboard_config.json")
    args = parser.parse_args()

    result = compile_config(args.config)
    print(f"Vertex AI Project: {result['vertex_ai_project_id']}")
    print("=" * 60)
    print(result["task_string"])
    print("=" * 60)
