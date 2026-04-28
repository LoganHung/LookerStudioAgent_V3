#!/usr/bin/env python3
"""
validate_config.py - Validates dashboard_config.json before Looker Studio automation.

Checks:
  - Required fields exist and are non-empty
  - chart_color / background_color are valid hex codes
  - legend_position is one of the allowed values
  - chart_type is a recognized type
  - metrics / dimensions arrays are non-empty (with scorecard exception for dimensions)
  - responsive_rows indices are valid and cover all visualizations

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
VALID_LEGEND_POSITIONS = {"top", "bottom", "right"}

# Valid filter conditions for chart-level filters
VALID_FILTER_CONDITIONS = {
    "equals", "not_equals", "contains", "not_contains",
    "starts_with", "ends_with", "in", "not_in", "between",
    "greater_than", "greater_than_or_equal",
    "less_than", "less_than_or_equal",
    "is_null", "is_not_null", "regex",
}

# Valid metric aggregation types
VALID_AGGREGATIONS = {"sum", "avg", "count", "count distinct", "min", "max", "none", "auto"}

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

def validate(config_path: str) -> tuple[list[str], list[str]] | list[str]:
    """Return (errors, warnings) or just errors for backward compat.

    Warnings are non-blocking issues (e.g. invalid config for chart type).
    Errors block execution.
    """
    errors = []
    warnings = []

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

    # ── 3. calculated_fields (optional) ─────────────────────────────────────
    calc_fields = config.get("calculated_fields")
    if calc_fields is not None:
        if not isinstance(calc_fields, list):
            errors.append("calculated_fields: must be an array")
        else:
            for cf_idx, cf in enumerate(calc_fields):
                cfpfx = f"calculated_fields[{cf_idx}]"
                if not isinstance(cf, dict):
                    errors.append(f"{cfpfx}: must be a JSON object")
                    continue
                if not is_nonempty_string(cf.get("field_name", "")):
                    errors.append(f"{cfpfx}.field_name: required and must be non-empty")
                if not is_nonempty_string(cf.get("formula", "")):
                    errors.append(f"{cfpfx}.formula: required and must be non-empty")

    # ── 4. visualizations ────────────────────────────────────────────────────
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
                        if isinstance(m, dict):
                            if not is_nonempty_string(m.get("name", "")):
                                errors.append(f"{pfx}.metrics[{m_idx}].name: required and must be non-empty")
                            agg = m.get("aggregation")
                            if agg is not None and str(agg).strip().lower() not in VALID_AGGREGATIONS:
                                errors.append(f"{pfx}.metrics[{m_idx}].aggregation: '{agg}' must be one of {sorted(VALID_AGGREGATIONS)}")
                        elif not is_nonempty_string(m):
                            errors.append(f"{pfx}.metrics[{m_idx}]: must be a non-empty string or object with 'name'")

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

            # special_configurations (optional; validate contents if present)
            sc = viz.get("special_configurations")
            if sc is not None:
                if not isinstance(sc, dict):
                    errors.append(f"{pfx}.special_configurations: must be a JSON object")
                else:
                    _validate_special_config(sc, pfx, errors)

    # ── 4b. Chart-type constraint warnings (non-blocking) ──────────────────
    from task_compiler import (
        _canonical, VALID_CONFIGS_BY_CHART, CHART_DATA_LIMITS, _FILTERABLE_CONFIG_KEYS
    )
    for idx, viz in enumerate(vizs):
        if not isinstance(viz, dict):
            continue
        ct_raw = viz.get("chart_type", "").strip()
        canonical = _canonical(ct_raw)
        pfx = f"visualizations[{idx}]"

        # Warn about invalid special_configurations
        sc = viz.get("special_configurations", {})
        valid_keys = VALID_CONFIGS_BY_CHART.get(canonical, set())
        if valid_keys and isinstance(sc, dict):
            for key in sc:
                if key in _FILTERABLE_CONFIG_KEYS and key not in valid_keys and sc.get(key):
                    warnings.append(
                        f"{pfx}.special_configurations.{key}: "
                        f"'{key}' is not available for '{ct_raw}' — will be skipped"
                    )

        # Warn about excess metrics/dimensions
        limits = CHART_DATA_LIMITS.get(canonical, {})
        max_m = limits.get("max_metrics")
        max_d = limits.get("max_dimensions")
        metrics = viz.get("metrics", [])
        dims = viz.get("dimensions", [])
        if max_m is not None and isinstance(metrics, list) and len(metrics) > max_m:
            warnings.append(
                f"{pfx}: {ct_raw} supports max {max_m} metric(s), "
                f"but {len(metrics)} provided — extras will be dropped"
            )
        if max_d is not None and isinstance(dims, list) and len(dims) > max_d:
            warnings.append(
                f"{pfx}: {ct_raw} supports max {max_d} dimension(s), "
                f"but {len(dims)} provided — extras will be dropped"
            )

    # ── 5. responsive_rows ─────────────────────────────────────────────────
    rows = config.get("responsive_rows")
    if rows is not None:
        if not isinstance(rows, list):
            errors.append("responsive_rows: must be an array of arrays")
        else:
            all_indices = []
            for r_idx, row in enumerate(rows):
                rpfx = f"responsive_rows[{r_idx}]"
                if not isinstance(row, list):
                    errors.append(f"{rpfx}: must be an array of visualization indices")
                    continue
                for v_idx in row:
                    if not isinstance(v_idx, int) or v_idx < 0:
                        errors.append(f"{rpfx}: index {v_idx} must be a non-negative integer")
                    elif len(vizs) > 0 and v_idx >= len(vizs):
                        errors.append(f"{rpfx}: index {v_idx} is out of bounds (only {len(vizs)} visualizations)")
                    all_indices.append(v_idx)

            # Check for duplicates
            seen = set()
            for idx in all_indices:
                if idx in seen:
                    errors.append(f"responsive_rows: index {idx} appears more than once")
                seen.add(idx)

            # Check all vizs are covered
            if len(vizs) > 0:
                missing = set(range(len(vizs))) - seen
                if missing:
                    errors.append(
                        f"responsive_rows: visualization indices {sorted(missing)} "
                        f"are not assigned to any row"
                    )

    return errors, warnings


def _validate_special_config(sc: dict, pfx: str, errors: list) -> None:
    for color_field in ("chart_color", "font_color", "background_color"):
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

    errors, warnings = validate(args.config)
    valid = len(errors) == 0

    if args.json_output:
        print(json.dumps({"valid": valid, "errors": errors, "warnings": warnings}, indent=2))
        sys.exit(0 if valid else 1)

    if valid:
        print("VALID")
    else:
        print("INVALID")
        for msg in errors:
            print(f"  \u2717 {msg}")

    if warnings:
        print("\n[Warnings — will be auto-filtered during compilation]")
        for msg in warnings:
            print(f"  \u26a0 {msg}")

    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
