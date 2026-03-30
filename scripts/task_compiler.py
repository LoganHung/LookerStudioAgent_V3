"""
Task Compiler for Looker Studio Automation (Responsive Layout)

Compiles dashboard_config.json into a single concise task string
using the Looker Studio UI Playbook for exact chart type names.
"""

import json
import os
import re
import sys
from datetime import datetime

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
        if sc.get("font_color"):
            sc["font_color"] = resolve_color(sc["font_color"])
        if sc.get("background_color"):
            sc["background_color"] = resolve_color(sc["background_color"])
    return config


def load_playbook(playbook_path: str = None) -> dict:
    if playbook_path is None:
        playbook_path = os.path.join(os.path.dirname(__file__), "looker_studio_playbook.json")
    with open(playbook_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_metric(m) -> tuple[str, str | None]:
    """Return (name, aggregation) from a metric entry (string or dict)."""
    if isinstance(m, dict):
        return m.get("name", ""), m.get("aggregation")
    return str(m), None


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
    steps = [step.format(**(params or {})) for step in steps]
    return steps


CONTROL_TYPES = {
    "dropdown_list", "drop_down", "dropdown", "drop-down list",
    "fixed_size_list", "fixed-size list", "fixed size list",
    "checkbox", "checkbox_control", "checkbox control",
    "date_range_control", "date_range", "date_control",
}
TEXT_TYPES = {"text", "text_box"}

# ── Chart-type normalization ──────────────────────────────────────────────────
# Maps all known aliases to a canonical key for lookup in constraint tables.
_CANONICAL_CHART_TYPE = {
    "scorecard": "scorecard", "kpi": "scorecard",
    "bar": "bar", "bar chart": "bar", "horizontal bar": "bar",
    "column": "bar", "column chart": "bar",
    "stacked_bar": "bar", "stacked bar": "bar", "stacked bar chart": "bar",
    "100_stacked_bar": "bar", "100% stacked bar": "bar",
    "stacked_column": "bar", "stacked column": "bar", "stacked column chart": "bar",
    "100_stacked_column": "bar",
    "line": "line", "line chart": "line",
    "combo": "line", "combo chart": "line",
    "time_series": "time_series", "time series": "time_series", "time series chart": "time_series",
    "sparkline": "time_series",
    "area": "area", "area chart": "area",
    "stacked_area": "area", "stacked area": "area", "stacked area chart": "area",
    "100_stacked_area": "area",
    "pie": "pie", "pie chart": "pie",
    "donut": "pie", "donut chart": "pie",
    "waterfall": "waterfall", "waterfall chart": "waterfall",
    "scatter": "scatter", "scatter chart": "scatter",
    "bubble": "scatter", "bubble chart": "scatter",
    "geo": "geo", "geo chart": "geo", "map": "geo",
    "google_maps": "geo", "google maps": "geo",
    "gauge": "gauge",
    "bullet": "bullet", "bullet chart": "bullet",
    "funnel": "funnel",
    "treemap": "treemap",
    "table": "table",
    "pivot_table": "pivot_table", "pivot table": "pivot_table",
}


def _canonical(chart_type_raw: str) -> str:
    """Return canonical chart key for constraint lookups."""
    return _CANONICAL_CHART_TYPE.get(chart_type_raw.strip().lower(), "unknown")


# ── Per-chart-type valid special_configurations (from Looker Studio docs) ─────
VALID_CONFIGS_BY_CHART: dict[str, set[str]] = {
    "scorecard":   {"font_size", "font_color", "chart_color", "background_color", "add_shadow", "compact_numbers", "others"},
    "bar":         {"font_size", "font_color", "chart_color", "background_color", "show_x_axis_title", "show_y_axis_title", "add_shadow", "legend_position", "show_data_labels", "compact_numbers", "cross_filtering", "others"},
    "line":        {"font_size", "font_color", "chart_color", "background_color", "show_x_axis_title", "show_y_axis_title", "add_shadow", "legend_position", "show_data_labels", "compact_numbers", "cross_filtering", "others"},
    "time_series": {"font_size", "font_color", "chart_color", "background_color", "show_x_axis_title", "show_y_axis_title", "add_shadow", "legend_position", "show_data_labels", "compact_numbers", "cross_filtering", "others"},
    "area":        {"font_size", "font_color", "chart_color", "background_color", "show_x_axis_title", "show_y_axis_title", "add_shadow", "legend_position", "show_data_labels", "compact_numbers", "cross_filtering", "others"},
    "pie":         {"font_size", "font_color", "chart_color", "background_color", "add_shadow", "legend_position", "show_data_labels", "cross_filtering", "others"},
    "waterfall":   {"font_size", "font_color", "chart_color", "background_color", "show_x_axis_title", "show_y_axis_title", "add_shadow", "show_data_labels", "compact_numbers", "cross_filtering", "others"},
    "scatter":     {"font_size", "font_color", "chart_color", "background_color", "show_x_axis_title", "show_y_axis_title", "add_shadow", "legend_position", "cross_filtering", "others"},
    "geo":         {"chart_color", "background_color", "add_shadow", "legend_position", "cross_filtering", "others"},
    "gauge":       {"font_size", "font_color", "chart_color", "background_color", "add_shadow", "compact_numbers", "others"},
    "bullet":      {"font_size", "font_color", "chart_color", "background_color", "add_shadow", "show_data_labels", "compact_numbers", "others"},
    "funnel":      {"font_size", "font_color", "chart_color", "background_color", "add_shadow", "legend_position", "show_data_labels", "compact_numbers", "cross_filtering", "others"},
    "treemap":     {"font_size", "font_color", "chart_color", "background_color", "add_shadow", "legend_position", "cross_filtering", "others"},
    "table":       {"font_size", "font_color", "background_color", "add_shadow", "compact_numbers", "cross_filtering", "others"},
    "pivot_table": {"font_size", "font_color", "background_color", "add_shadow", "compact_numbers", "others"},
}

# ── Per-chart-type data limits ────────────────────────────────────────────────
CHART_DATA_LIMITS: dict[str, dict[str, int]] = {
    "scorecard":   {"max_metrics": 1, "max_dimensions": 1},
    "bar":         {"max_metrics": 20, "max_dimensions": 2},
    "line":        {"max_metrics": 5, "max_dimensions": 2},
    "time_series": {"max_metrics": 5, "max_dimensions": 2},
    "area":        {"max_metrics": 5, "max_dimensions": 2},
    "pie":         {"max_metrics": 1, "max_dimensions": 1},
    "waterfall":   {"max_metrics": 1, "max_dimensions": 1},
    "scatter":     {"max_metrics": 3, "max_dimensions": 3},
    "geo":         {"max_metrics": 1, "max_dimensions": 1},
    "gauge":       {"max_metrics": 1, "max_dimensions": 0},
    "bullet":      {"max_metrics": 1, "max_dimensions": 0},
    "funnel":      {"max_metrics": 1, "max_dimensions": 1},
    "treemap":     {"max_metrics": 2, "max_dimensions": 2},
    "table":       {"max_metrics": 50, "max_dimensions": 50},
    "pivot_table": {"max_metrics": 50, "max_dimensions": 50},
}

# Config keys that we check for validity (excludes 'others' — always allowed)
_FILTERABLE_CONFIG_KEYS = {
    "font_size", "font_color", "chart_color", "background_color",
    "show_x_axis_title", "show_y_axis_title", "add_shadow",
    "legend_position", "show_data_labels", "compact_numbers", "cross_filtering",
}


def compile_config(config_path: str, playbook_path: str = None) -> dict:
    """Compile a dashboard config into a single task string (responsive layout)."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    config = translate_config(config)
    playbook = load_playbook(playbook_path)
    steps = []
    step_num = [0]
    skipped: list[str] = []  # collects skipped config/data warnings

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

    # === Enable Responsive Layout ===
    add_procedure("enable_responsive_layout")

    # === Calculated Fields (create before charts via data panel) ===
    calculated_fields = config.get("calculated_fields", [])
    if calculated_fields:
        add("Click on an empty area of the canvas to deselect any selected chart")
        for cf in calculated_fields:
            add_procedure("add_calculated_field", {
                "field_name": cf.get("field_name", ""),
                "formula": cf.get("formula", ""),
            })

    # === Charts (Responsive: grouped by rows/sections) ===
    visualizations = config.get("visualizations", [])
    calc_field_names = {cf.get("field_name", "") for cf in calculated_fields}

    # Default: each viz in its own row if responsive_rows not specified
    responsive_rows = config.get("responsive_rows", [[i] for i in range(len(visualizations))])

    for row_idx, row_viz_indices in enumerate(responsive_rows):
        if row_idx > 0:
            add_procedure("add_new_section")

        for pos_in_row, viz_idx in enumerate(row_viz_indices):
            is_first_in_section = (pos_in_row == 0)

            if viz_idx >= len(visualizations):
                continue
            viz = visualizations[viz_idx]
            chart_type_raw = viz.get("chart_type", "").strip()

            # Auto-detect chart type from title if missing
            if not chart_type_raw:
                title_lower = viz.get("title", "").lower()
                if "pie" in title_lower: chart_type_raw = "pie"
                elif "line" in title_lower or "trend" in title_lower: chart_type_raw = "time_series"
                elif "scorecard" in title_lower or "kpi" in title_lower: chart_type_raw = "scorecard"
                elif "table" in title_lower: chart_type_raw = "table"
                elif "geo" in title_lower or "map" in title_lower: chart_type_raw = "geo"
                else: chart_type_raw = "bar"

            chart_type_label = resolve_chart_type(chart_type_raw, playbook)
            canonical = _canonical(chart_type_raw)
            viz_label = f"viz[{viz_idx}] ({chart_type_raw})"

            # ── Filter invalid special_configurations ──
            sc = viz.get("special_configurations", {})
            valid_keys = VALID_CONFIGS_BY_CHART.get(canonical, set())
            if valid_keys and sc:
                for key in list(sc.keys()):
                    if key in _FILTERABLE_CONFIG_KEYS and key not in valid_keys and sc.get(key):
                        skipped.append(f"{viz_label}: '{key}' is not available for {chart_type_raw} — skipped")
                        sc[key] = None  # neutralize so it won't generate steps

            # ── Truncate excess metrics/dimensions ──
            limits = CHART_DATA_LIMITS.get(canonical, {})
            max_m = limits.get("max_metrics")
            max_d = limits.get("max_dimensions")
            metrics = viz.get("metrics", [])
            dimensions = viz.get("dimensions", [])
            if max_m is not None and len(metrics) > max_m:
                dropped = [str(parse_metric(m)[0]) for m in metrics[max_m:]]
                skipped.append(f"{viz_label}: max {max_m} metric(s) allowed — dropped {dropped}")
                metrics = metrics[:max_m]
                viz["metrics"] = metrics
            if max_d is not None and len(dimensions) > max_d:
                dropped = dimensions[max_d:]
                skipped.append(f"{viz_label}: max {max_d} dimension(s) allowed — dropped {dropped}")
                dimensions = dimensions[:max_d]
                viz["dimensions"] = dimensions

            # Place the element — first in section uses placeholder button, rest use section's add-chart
            if chart_type_raw.lower() in TEXT_TYPES:
                text_content = viz.get("title", "") or viz.get("text_content", "")
                add(f"Add a text box using the Text toolbar button and set its content to '{text_content}'")
                continue
            elif chart_type_raw.lower() in CONTROL_TYPES:
                control_field = viz.get("control_field", "") or (viz.get("dimensions", []) or [""])[0]
                if is_first_in_section:
                    add_procedure("add_first_control_to_section", {"chart_type": chart_type_label})
                else:
                    add_procedure("add_another_control_to_section", {"chart_type": chart_type_label})
                if control_field:
                    add(f"Set the control's field to '{control_field}'")
            else:
                if is_first_in_section:
                    add_procedure("add_first_chart_to_section", {"chart_type": chart_type_label})
                else:
                    add_procedure("add_another_chart_to_section", {"chart_type": chart_type_label})

            # Dimensions
            dimensions = viz.get("dimensions", [])
            if dimensions:
                add_procedure("set_dimension", {"dimension_name": dimensions[0]})
                for dim in dimensions[1:]:
                    add_procedure("add_dimension", {"dimension_name": dim})

            # Metrics (aggregation embedded inline in each metric entry)
            metrics = viz.get("metrics", [])
            if metrics:
                name, agg = parse_metric(metrics[0])
                if agg and name not in calc_field_names:
                    add_procedure("set_metric_with_aggregation", {"metric_name": name, "aggregation_type": agg})
                else:
                    add_procedure("set_metric", {"metric_name": name})
                for m in metrics[1:]:
                    name, agg = parse_metric(m)
                    if agg and name not in calc_field_names:
                        add_procedure("add_metric_with_aggregation", {"metric_name": name, "aggregation_type": agg})
                    else:
                        add_procedure("add_metric", {"metric_name": name})

            # Sorting
            sort_by = viz.get("sort_by")
            sort_order = viz.get("sort_order", "Descending")
            if sort_by:
                add_procedure("set_sort", {"sort_field": sort_by, "sort_order": sort_order})

            # Row limit
            row_limit = viz.get("row_limit")
            if row_limit:
                add_procedure("set_row_limit", {"row_limit": str(row_limit)})

            # Chart-level filters
            filters = viz.get("filters", [])
            for filt in filters:
                condition = filt.get("condition", "equals").lower()
                if condition == "between":
                    parts = [v.strip() for v in str(filt.get("value", "")).split(",")]
                    add_procedure("add_chart_filter_between", {
                        "filter_type": filt.get("type", "include").capitalize(),
                        "field_name": filt.get("field", ""),
                        "value_start": parts[0] if len(parts) > 0 else "",
                        "value_end": parts[1] if len(parts) > 1 else "",
                    })
                else:
                    add_procedure("add_chart_filter", {
                        "filter_type": filt.get("type", "include").capitalize(),
                        "field_name": filt.get("field", ""),
                        "condition": filt.get("condition", "equals"),
                        "value": str(filt.get("value", "")),
                    })

            # Setup-level configurations (sc already set above during filtering)
            if sc.get("compact_numbers"):
                for s in expand_procedure("style_toggle_compact_numbers", playbook):
                    add(s)
            if sc.get("cross_filtering"):
                for s in expand_procedure("toggle_cross_filtering", playbook):
                    add(s)

            # Style tab
            title = viz.get("title", "")
            style_parts = []
            if title:
                style_parts.extend(expand_procedure("style_set_title", playbook, {"title_text": title}))
            if sc.get("chart_color") and sc["chart_color"].lower() not in ("default", "none", ""):
                style_parts.extend(expand_procedure("style_set_color", playbook, {"color_value": sc["chart_color"]}))
            if sc.get("font_color") and sc["font_color"].lower() not in ("default", "none", ""):
                style_parts.extend(expand_procedure("style_set_font_color", playbook, {"color_value": sc["font_color"]}))
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
                add("Switch to 'Style' tab. " + " ".join(style_parts))

        # After all charts in this row, set section style to stretch
        if len(row_viz_indices) > 1:
            add_procedure("set_section_style_stretch")

    # === Footer: creation timestamp text box ===
    created_on = datetime.now().strftime("%m/%d/%Y")
    footer_text = f"Looker Studio Agent created the dashboard on {created_on}"
    add_procedure("add_new_section")
    add_procedure("add_text_to_section", {"text_content": footer_text})

    # === Report Title (canvas placeholder + editor title bar) ===
    report_title = config.get("report_title")
    if report_title:
        add_procedure("set_report_title", {"report_title": report_title})
        add_procedure("set_editor_title", {"report_title": report_title})

    # Output skipped warnings to stderr
    if skipped:
        print("\n[Config Filter Warnings]", file=sys.stderr)
        for msg in skipped:
            print(f"  ⚠ {msg}", file=sys.stderr)
        print("", file=sys.stderr)

    task_string = "\n".join(steps)

    return {
        "task_string": task_string,
        "vertex_ai_project_id": config.get("vertex_ai_project_id", ""),
        "user_data_dir": config.get("user_data_dir", ""),
        "skipped_configs": skipped,
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
