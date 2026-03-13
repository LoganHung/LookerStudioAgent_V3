#!/usr/bin/env python3
"""
validate_config.py - Validates dashboard_config.json before Looker Studio automation.

Checks:
  - Required fields exist and are non-empty
  - chart_color / background_color are valid hex codes
  - legend_position is one of the allowed values
  - chart_type is a recognized type
  - metrics / dimensions arrays are non-empty (with scorecard exception for dimensions)
  - layout_instructions count matches visualizations count

Exit codes:
  0  VALID
  1  INVALID (validation errors found)
  2  Usage / file error
"""

import argparse
import json
import os
import re
import sys

# ── Constants ──────────────────────────────────────────────────────────────────

# Non-data element types (no metrics/dimensions needed)
NON_DATA_TYPES = {"text", "text_box", "date_range_control", "date_range", "date_control"}

# Interactive control types (use control_field instead of metrics/dimensions)
CONTROL_TYPES = {
    "dropdown_list", "drop_down", "dropdown", "drop-down list",
    "fixed_size_list", "fixed-size list", "fixed size list",
    "checkbox", "checkbox_control", "checkbox control",
}

# Chart types that do not require at least one dimension
DIMENSION_OPTIONAL_TYPES = {"scorecard", "kpi"} | NON_DATA_TYPES | CONTROL_TYPES

# Chart types that do not require at least one metric
METRIC_OPTIONAL_TYPES = NON_DATA_TYPES | CONTROL_TYPES

# Valid legend_position values (Looker Studio supported values per WORKFLOW.md)
VALID_LEGEND_POSITIONS = {"top", "down", "right", "left"}

# Valid filter conditions for chart-level filters
VALID_FILTER_CONDITIONS = {
    "equals", "not_equals", "contains", "not_contains",
    "starts_with", "ends_with", "in", "not_in",
    "greater_than", "greater_than_or_equal",
    "less_than", "less_than_or_equal",
    "is_null", "is_not_null", "regex",
}

# Valid metric aggregation types
VALID_AGGREGATIONS = {"sum", "avg", "count", "count_distinct", "min", "max", "none", "auto"}

# All recognized chart type keys and aliases (mirrors looker_studio_playbook.json)
KNOWN_CHART_TYPES = {
    # canonical keys
    "table", "pivot_table", "scorecard", "time_series", "bar",
    "stacked_bar", "100_stacked_bar", "column", "stacked_column",
    "100_stacked_column", "pie", "donut", "geo", "google_maps",
    "line", "sparkline", "combo", "area", "stacked_area",
    "100_stacked_area", "scatter", "bubble", "bullet", "treemap", "gauge",
    # special UI elements
    "text", "text_box", "date_range_control", "date_range", "date_control",
    # common natural-language aliases
    "bar chart", "column chart", "line chart", "time series", "time series chart",
    "pie chart", "donut chart", "kpi", "pivot table", "geo chart",
    "map", "google maps", "scatter chart", "bubble chart", "area chart",
    "stacked bar", "stacked bar chart", "100% stacked bar", "stacked column",
    "stacked column chart", "stacked area", "stacked area chart",
    "combo chart", "bullet chart", "horizontal bar",
    "waterfall", "waterfall chart",
    # filter controls
    "dropdown_list", "drop_down", "dropdown", "drop-down list",
    "fixed_size_list", "fixed-size list", "fixed size list",
    "checkbox", "checkbox_control", "checkbox control",
}

HEX_RE = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_valid_hex(value: str) -> bool:
    return bool(HEX_RE.match(value.strip()))


def is_nonempty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


# ── Core validation ────────────────────────────────────────────────────────────

def validate(config_path: str) -> list[str]:
    """Return a list of error messages. Empty list means the config is valid."""
    errors = []

    if not os.path.isfile(config_path):
        return [f"File not found: {config_path}"]

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    if not isinstance(config, dict):
        return ["Config root must be a JSON object"]

    # ── 1. vertex_ai_project_id ──────────────────────────────────────────────
    if not is_nonempty_string(config.get("vertex_ai_project_id", "")):
        errors.append("vertex_ai_project_id: required and must be non-empty")

    # ── 2. data_source ───────────────────────────────────────────────────────
    ds = config.get("data_source")
    if not isinstance(ds, dict):
        errors.append("data_source: required object is missing or not an object")
    else:
        for field in ("project_id", "dataset", "table_name"):
            if not is_nonempty_string(ds.get(field, "")):
                errors.append(f"data_source.{field}: required and must be non-empty")

    # ── 3. visualizations ────────────────────────────────────────────────────
    vizs = config.get("visualizations")
    if not isinstance(vizs, list) or len(vizs) == 0:
        errors.append("visualizations: required and must be a non-empty array")
        vizs = []
    else:
        for idx, viz in enumerate(vizs):
            pfx = f"visualizations[{idx}]"

            if not isinstance(viz, dict):
                errors.append(f"{pfx}: each item must be a JSON object")
                continue

            # chart_type
            ct_raw = viz.get("chart_type", "")
            if not is_nonempty_string(ct_raw):
                errors.append(f"{pfx}.chart_type: required and must be non-empty")
                ct_raw = ""
            elif ct_raw.strip().lower() not in KNOWN_CHART_TYPES:
                errors.append(
                    f"{pfx}.chart_type: '{ct_raw}' is not a recognized chart type"
                )

            ct_lower = ct_raw.strip().lower()

            # metrics (optional for controls and non-data types)
            metrics = viz.get("metrics")
            if ct_lower not in METRIC_OPTIONAL_TYPES:
                if not isinstance(metrics, list):
                    errors.append(f"{pfx}.metrics: required and must be an array")
                elif len(metrics) == 0:
                    errors.append(f"{pfx}.metrics: must contain at least one metric")
                else:
                    for m_idx, m in enumerate(metrics):
                        if not is_nonempty_string(m):
                            errors.append(f"{pfx}.metrics[{m_idx}]: must be a non-empty string")

            # dimensions (optional for scorecards, controls, and non-data types)
            dims = viz.get("dimensions")
            if ct_lower not in DIMENSION_OPTIONAL_TYPES:
                if not isinstance(dims, list):
                    errors.append(f"{pfx}.dimensions: required and must be an array")
                elif len(dims) == 0:
                    errors.append(
                        f"{pfx}.dimensions: must contain at least one dimension "
                        f"(use chart_type 'scorecard' or 'kpi' if dimensions are intentionally empty)"
                    )
                else:
                    for d_idx, d in enumerate(dims):
                        if not is_nonempty_string(d):
                            errors.append(f"{pfx}.dimensions[{d_idx}]: must be a non-empty string")

            # control_field (required for control types)
            if ct_lower in CONTROL_TYPES:
                control_field = viz.get("control_field", "")
                if not is_nonempty_string(control_field):
                    errors.append(f"{pfx}.control_field: required for control type '{ct_raw}'")

            # filters (optional; validate if present)
            filters = viz.get("filters")
            if filters is not None:
                if not isinstance(filters, list):
                    errors.append(f"{pfx}.filters: must be an array")
                else:
                    for f_idx, filt in enumerate(filters):
                        fpfx = f"{pfx}.filters[{f_idx}]"
                        if not isinstance(filt, dict):
                            errors.append(f"{fpfx}: must be a JSON object")
                            continue
                        ft = filt.get("type", "")
                        if not is_nonempty_string(ft) or ft.strip().lower() not in ("include", "exclude"):
                            errors.append(f"{fpfx}.type: must be 'include' or 'exclude'")
                        if not is_nonempty_string(filt.get("field", "")):
                            errors.append(f"{fpfx}.field: required and must be non-empty")
                        cond = filt.get("condition", "")
                        if not is_nonempty_string(cond) or cond.strip().lower() not in VALID_FILTER_CONDITIONS:
                            errors.append(f"{fpfx}.condition: must be one of {sorted(VALID_FILTER_CONDITIONS)}")
                        if cond and cond.strip().lower() not in ("is_null", "is_not_null"):
                            if not is_nonempty_string(str(filt.get("value", ""))):
                                errors.append(f"{fpfx}.value: required for condition '{cond}'")

            # metric_aggregations (optional; validate if present)
            metric_aggs = viz.get("metric_aggregations")
            if metric_aggs is not None:
                if not isinstance(metric_aggs, dict):
                    errors.append(f"{pfx}.metric_aggregations: must be a JSON object")
                else:
                    for field_name, agg_type in metric_aggs.items():
                        if not is_nonempty_string(str(agg_type)) or str(agg_type).strip().lower() not in VALID_AGGREGATIONS:
                            errors.append(
                                f"{pfx}.metric_aggregations.{field_name}: "
                                f"'{agg_type}' must be one of {sorted(VALID_AGGREGATIONS)}"
                            )

            # special_configurations (optional; validate contents if present)
            sc = viz.get("special_configurations")
            if sc is not None:
                if not isinstance(sc, dict):
                    errors.append(f"{pfx}.special_configurations: must be a JSON object")
                else:
                    _validate_special_config(sc, pfx, errors)

    # ── 4. layout_instructions ───────────────────────────────────────────────
    layout = config.get("layout_instructions")
    if not isinstance(layout, list) or len(layout) == 0:
        errors.append("layout_instructions: required and must be a non-empty array")
    elif len(vizs) > 0 and len(layout) != len(vizs):
        errors.append(
            f"layout_instructions: has {len(layout)} entr{'y' if len(layout) == 1 else 'ies'} "
            f"but visualizations has {len(vizs)}; counts must match 1-to-1"
        )

    return errors


def _validate_special_config(sc: dict, pfx: str, errors: list) -> None:
    for color_field in ("chart_color", "background_color"):
        val = sc.get(color_field, "")
        if val and is_nonempty_string(val) and val.strip().lower() not in ("default", "none"):
            if not is_valid_hex(val.strip()):
                errors.append(
                    f"{pfx}.special_configurations.{color_field}: "
                    f"'{val}' is not a valid hex color code (expected format: #RRGGBB or #RGB)"
                )

    legend = sc.get("legend_position", "")
    if legend and is_nonempty_string(legend):
        if legend.strip().lower() not in VALID_LEGEND_POSITIONS:
            errors.append(
                f"{pfx}.special_configurations.legend_position: "
                f"'{legend}' is not valid; must be one of {sorted(VALID_LEGEND_POSITIONS)}"
            )

    font_size = sc.get("font_size", "")
    if font_size and is_nonempty_string(str(font_size)):
        try:
            if float(str(font_size).strip()) <= 0:
                raise ValueError
        except ValueError:
            errors.append(
                f"{pfx}.special_configurations.font_size: "
                f"'{font_size}' must be a positive number"
            )


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate dashboard_config.json before Looker Studio automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python validate_config.py --config .looker-automation/dashboard_config.json
  python validate_config.py --config data.json --json

exit codes:
  0  VALID   — config is ready for execution
  1  INVALID — one or more validation errors found
  2  usage / file error
""",
    )
    parser.add_argument("--config", required=True, help="Path to dashboard_config.json")
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Emit results as JSON (useful for programmatic consumers)"
    )
    args = parser.parse_args()

    errors = validate(args.config)
    valid = len(errors) == 0

    if args.json_output:
        print(json.dumps({"valid": valid, "errors": errors}, indent=2))
        sys.exit(0 if valid else 1)

    if valid:
        print("VALID")
        sys.exit(0)
    else:
        print("INVALID")
        for msg in errors:
            print(f"  \u2717 {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
