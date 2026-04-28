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

# ── Constraints loaded from playbook (single source of truth) ────────────────

def _load_constraints(playbook: dict) -> tuple[dict, dict[str, set[str]], dict[str, dict]]:
    """Load canonical aliases, style constraints, and data limits from playbook."""
    canonical_aliases = playbook.get("chart_canonical_aliases", {})
    style_constraints = {
        k: set(v) for k, v in playbook.get("chart_style_constraints", {}).items()
    }
    data_limits = playbook.get("chart_data_limits", {})
    return canonical_aliases, style_constraints, data_limits


def _canonical(chart_type_raw: str, playbook: dict) -> str:
    """Return canonical chart key for constraint lookups."""
    aliases = playbook.get("chart_canonical_aliases", {})
    return aliases.get(chart_type_raw.strip().lower(), "unknown")


# Config keys that we check for validity (excludes 'others' — always allowed)
_FILTERABLE_CONFIG_KEYS = {
    "font_size", "font_color", "chart_color", "background_color",
    "show_x_axis_title", "show_y_axis_title", "add_shadow",
    "legend_position", "show_data_labels", "compact_numbers", "cross_filtering",
}


def _compile_viz_steps(
    viz: dict, viz_idx: int, is_first_in_section: bool,
    calc_field_names: set, playbook: dict, skipped: list,
    placed_by_insert: bool = False,
) -> list[str]:
    """Compile all steps for a single visualization. Returns raw step strings (no numbering)."""
    steps = []
    chart_type_raw = viz.get("chart_type", "").strip()

    if not chart_type_raw:
        title_lower = viz.get("title", "").lower()
        if "pie" in title_lower: chart_type_raw = "pie"
        elif "line" in title_lower or "trend" in title_lower: chart_type_raw = "time_series"
        elif "scorecard" in title_lower or "kpi" in title_lower: chart_type_raw = "scorecard"
        elif "table" in title_lower: chart_type_raw = "table"
        elif "geo" in title_lower or "map" in title_lower: chart_type_raw = "geo"
        else: chart_type_raw = "bar"

    chart_type_label = resolve_chart_type(chart_type_raw, playbook)
    canonical = _canonical(chart_type_raw, playbook)
    viz_label = f"viz[{viz_idx}] ({chart_type_raw})"

    # Load constraints from playbook (single source of truth)
    _, style_constraints, data_limits = _load_constraints(playbook)

    # Filter invalid special_configurations
    sc = viz.get("special_configurations", {})
    valid_keys = style_constraints.get(canonical, set())
    if valid_keys and sc:
        for key in list(sc.keys()):
            if key in _FILTERABLE_CONFIG_KEYS and key not in valid_keys and sc.get(key):
                skipped.append(f"{viz_label}: '{key}' is not available for {chart_type_raw} — skipped")
                sc[key] = None

    # Truncate excess metrics/dimensions
    limits = data_limits.get(canonical, {})
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

    # Place element
    if chart_type_raw.lower() in TEXT_TYPES:
        text_content = viz.get("title", "") or viz.get("text_content", "")
        steps.append(f"Add a text box using the Text toolbar button and set its content to '{text_content}'")
        return steps
    elif chart_type_raw.lower() in CONTROL_TYPES:
        control_field = viz.get("control_field", "") or (viz.get("dimensions", []) or [""])[0]
        if is_first_in_section:
            steps.extend(expand_procedure("add_first_control_to_section", playbook, {"chart_type": chart_type_label}))
        else:
            steps.extend(expand_procedure("add_another_control_to_section", playbook, {"chart_type": chart_type_label}))
        if control_field:
            steps.append(f"Set the control's field to '{control_field}'")
    else:
        if not placed_by_insert:
            if is_first_in_section:
                steps.extend(expand_procedure("add_first_chart_to_section", playbook, {"chart_type": chart_type_label}))
            else:
                steps.extend(expand_procedure("add_another_chart_to_section", playbook, {"chart_type": chart_type_label}))

    # Dimensions
    dimensions = viz.get("dimensions", [])
    if dimensions:
        steps.extend(expand_procedure("set_dimension", playbook, {"dimension_name": dimensions[0]}))
        for dim in dimensions[1:]:
            steps.extend(expand_procedure("add_dimension", playbook, {"dimension_name": dim}))

    # Metrics
    metrics = viz.get("metrics", [])
    if metrics:
        name, agg = parse_metric(metrics[0])
        if agg and name not in calc_field_names:
            steps.extend(expand_procedure("set_metric_with_aggregation", playbook, {"metric_name": name, "aggregation_type": agg}))
        else:
            steps.extend(expand_procedure("set_metric", playbook, {"metric_name": name}))
        for m in metrics[1:]:
            name, agg = parse_metric(m)
            if agg and name not in calc_field_names:
                steps.extend(expand_procedure("add_metric_with_aggregation", playbook, {"metric_name": name, "aggregation_type": agg}))
            else:
                steps.extend(expand_procedure("add_metric", playbook, {"metric_name": name}))

    # Sorting
    sort_by = viz.get("sort_by")
    sort_order = viz.get("sort_order", "Descending")
    if sort_by:
        steps.extend(expand_procedure("set_sort", playbook, {"sort_field": sort_by, "sort_order": sort_order}))

    # Row limit
    row_limit = viz.get("row_limit")
    if row_limit:
        steps.extend(expand_procedure("set_row_limit", playbook, {"row_limit": str(row_limit)}))

    # Chart-level filters
    for filt in viz.get("filters", []):
        condition = filt.get("condition", "equals").lower()
        if condition == "between":
            parts = [v.strip() for v in str(filt.get("value", "")).split(",")]
            steps.extend(expand_procedure("add_chart_filter_between", playbook, {
                "filter_type": filt.get("type", "include").capitalize(),
                "field_name": filt.get("field", ""),
                "value_start": parts[0] if len(parts) > 0 else "",
                "value_end": parts[1] if len(parts) > 1 else "",
            }))
        else:
            steps.extend(expand_procedure("add_chart_filter", playbook, {
                "filter_type": filt.get("type", "include").capitalize(),
                "field_name": filt.get("field", ""),
                "condition": filt.get("condition", "equals"),
                "value": str(filt.get("value", "")),
            }))

    # Setup-level configurations
    if sc.get("compact_numbers"):
        steps.extend(expand_procedure("style_toggle_compact_numbers", playbook))
    if sc.get("cross_filtering"):
        steps.extend(expand_procedure("toggle_cross_filtering", playbook))

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
        style_parts.extend(expand_procedure("others", playbook, {"others": sc["other"]}))

    if style_parts:
        steps.append("Switch to 'Style' tab.")
        steps.extend(style_parts)

    return steps


CALC_FIELD_CAP = 10  # max calculated fields per phase


def compile_config_phased(config_path: str, playbook_path: str = None) -> dict:
    """Compile dashboard config into phases for sub-agent execution.

    Phase structure:
      - Phase 1:   Setup (create report, connect BigQuery, enable responsive layout)
      - Phase 2+:  Calculated fields (capped at CALC_FIELD_CAP per phase)
      - Phase N+:  One phase per responsive row (add section + configure all charts)
      - Footer + report title appended to last row phase

    Returns:
        {
            "phases": [{"name", "description", "steps": [str], "task_string": str}, ...],
            "vertex_ai_project_id": str,
            "user_data_dir": str,
            "skipped_configs": [str],
        }
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    config = translate_config(config)
    playbook = load_playbook(playbook_path)
    phases: list[dict] = []
    skipped: list[str] = []

    # === Phase 1: Setup ===
    ds = config.get("data_source", {})
    setup_steps = []
    setup_steps.extend(expand_procedure("create_blank_report", playbook))
    setup_steps.extend(expand_procedure("connect_bigquery", playbook, {
        "project_id": ds.get("project_id", ""),
        "dataset": ds.get("dataset", ""),
        "table": ds.get("table_name", ""),
    }))
    setup_steps.extend(expand_procedure("enable_responsive_layout", playbook))
    phases.append({
        "name": "Setup",
        "description": "Create blank report, connect BigQuery data source, enable responsive layout",
        "steps": setup_steps,
        "model_tier": "flash",
    })

    # === Phase 2+: Calculated Fields (capped at CALC_FIELD_CAP per phase) ===
    calculated_fields = config.get("calculated_fields", [])
    calc_field_names = {cf.get("field_name", "") for cf in calculated_fields}

    if calculated_fields:
        for batch_start in range(0, len(calculated_fields), CALC_FIELD_CAP):
            batch = calculated_fields[batch_start:batch_start + CALC_FIELD_CAP]
            batch_end = min(batch_start + CALC_FIELD_CAP, len(calculated_fields))
            cf_steps = []
            for cf in batch:
                cf_steps.extend(expand_procedure("add_calculated_field", playbook, {
                    "field_name": cf.get("field_name", ""),
                    "formula": cf.get("formula", "") + "  ",
                }))

            # Verification step: confirm all fields in this batch exist
            batch_field_names = [cf.get("field_name", "") for cf in batch]
            field_list_str = ", ".join(f"'{n}'" for n in batch_field_names)
            cf_steps.append(
                f"Verification: Read the Data panel on the right side and confirm these calculated fields exist: {field_list_str}. "
                f"If any field is missing, use the same 'Add a field' approach to create it with its formula."
            )

            phase_name = "Calculated Fields"
            if len(calculated_fields) > CALC_FIELD_CAP:
                phase_name += f" ({batch_start + 1}–{batch_end})"
            phases.append({
                "name": phase_name,
                "description": f"Add calculated fields: {', '.join(cf.get('field_name', '') for cf in batch)}",
                "steps": cf_steps,
                "model_tier": "flash",
            })

    # === Chart Creation Phase: all responsive rows in a single phase ===
    visualizations = config.get("visualizations", [])
    responsive_rows = config.get("responsive_rows", [[i] for i in range(len(visualizations))])

    chart_steps = []
    all_viz_labels = []

    total_rows = len(responsive_rows)
    for row_idx, row_viz_indices in enumerate(responsive_rows, start=1):
        if row_idx > 1:
            first_vi = row_viz_indices[0] if row_viz_indices else None
            first_viz = visualizations[first_vi] if first_vi is not None and first_vi < len(visualizations) else None
            first_chart_label = resolve_chart_type(first_viz.get("chart_type", "bar"), playbook) if first_viz else "Bar chart"
            chart_steps.extend(expand_procedure("add_new_section", playbook, {"chart_type": first_chart_label}))

        for pos_in_row, viz_idx in enumerate(row_viz_indices):
            if viz_idx >= len(visualizations):
                continue
            viz = visualizations[viz_idx]
            all_viz_labels.append(viz.get("title") or viz.get("chart_type", "unknown"))
            chart_steps.extend(_compile_viz_steps(
                viz, viz_idx, is_first_in_section=(pos_in_row == 0),
                calc_field_names=calc_field_names, playbook=playbook, skipped=skipped,
                placed_by_insert=(row_idx > 1 and pos_in_row == 0),
            ))

        if len(row_viz_indices) > 1:
            chart_steps.extend(expand_procedure("set_section_style_stretch", playbook))

    # === Footer + Report Title — appended to chart creation phase ===
    created_on = datetime.now().strftime("%m/%d/%Y")
    footer_text = f"Looker Studio Agent created the dashboard on {created_on}"
    chart_steps.extend(expand_procedure("add_text_to_section", playbook, {"text_content": footer_text}))

    description = f"Build all charts ({len(responsive_rows)} rows, {len(all_viz_labels)} charts) + footer"

    report_title = config.get("report_title")
    if report_title:
        chart_steps.extend(expand_procedure("set_report_title", playbook, {"report_title": report_title}))
        chart_steps.extend(expand_procedure("set_editor_title", playbook, {"report_title": report_title}))
        description += " + report title"

    phases.append({
        "name": "Chart Creation",
        "description": description,
        "steps": chart_steps,
        "model_tier": "pro",
    })

    # Add numbered task_string to each phase
    for phase in phases:
        phase["task_string"] = "\n".join(
            f"{i + 1}. {s}" for i, s in enumerate(phase["steps"])
        )

    if skipped:
        print("\n[Config Filter Warnings]", file=sys.stderr)
        for msg in skipped:
            print(f"  ⚠ {msg}", file=sys.stderr)
        print("", file=sys.stderr)

    return {
        "phases": phases,
        "vertex_ai_project_id": config.get("vertex_ai_project_id", ""),
        "user_data_dir": config.get("user_data_dir", ""),
        "skipped_configs": skipped,
    }


TODO_RULES_HEADER = ""


def generate_todo(phases: list[dict], todo_path: str) -> None:
    """Write todo.md with rules header + ALL phases and steps upfront (all unchecked)."""
    lines = [TODO_RULES_HEADER, "# Dashboard Build — Todo", ""]
    for i, phase in enumerate(phases):
        lines.append(f"## Phase {i + 1}: {phase['name']}")
        lines.append(f"_{phase['description']}_")
        lines.append("")
        for step in phase["steps"]:
            lines.append(f"- [ ] {step}")
        lines.append("")
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def update_todo_phase(todo_path: str, phase: dict) -> None:
    """Mark all steps of a completed phase as done in todo.md."""
    with open(todo_path, "r", encoding="utf-8") as f:
        content = f.read()
    for step in phase["steps"]:
        content = content.replace(f"- [ ] {step}", f"- [x] {step}", 1)
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write(content)


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
        for cf in calculated_fields:
            add_procedure("add_calculated_field", {
                "field_name": cf.get("field_name", ""),
                "formula": cf.get("formula", "") + "  ",
            })

    # === Charts (Responsive: grouped by rows/sections) ===
    visualizations = config.get("visualizations", [])
    calc_field_names = {cf.get("field_name", "") for cf in calculated_fields}

    # Default: each viz in its own row if responsive_rows not specified
    responsive_rows = config.get("responsive_rows", [[i] for i in range(len(visualizations))])

    for row_idx, row_viz_indices in enumerate(responsive_rows, start=1):
        if row_idx > 1:
            first_vi = row_viz_indices[0] if row_viz_indices else None
            first_viz_raw = visualizations[first_vi].get("chart_type", "bar").strip() if first_vi is not None and first_vi < len(visualizations) else "bar"
            add_procedure("add_new_section", {"chart_type": resolve_chart_type(first_viz_raw, playbook)})

        for pos_in_row, viz_idx in enumerate(row_viz_indices):
            is_first_in_section = (pos_in_row == 0)
            placed_by_insert = (row_idx > 1 and pos_in_row == 0)

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
            canonical = _canonical(chart_type_raw, playbook)
            viz_label = f"viz[{viz_idx}] ({chart_type_raw})"

            # Load constraints from playbook (single source of truth)
            _, style_constraints, data_limits = _load_constraints(playbook)

            # ── Filter invalid special_configurations ──
            sc = viz.get("special_configurations", {})
            valid_keys = style_constraints.get(canonical, set())
            if valid_keys and sc:
                for key in list(sc.keys()):
                    if key in _FILTERABLE_CONFIG_KEYS and key not in valid_keys and sc.get(key):
                        skipped.append(f"{viz_label}: '{key}' is not available for {chart_type_raw} — skipped")
                        sc[key] = None  # neutralize so it won't generate steps

            # ── Truncate excess metrics/dimensions ──
            limits = data_limits.get(canonical, {})
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
                if not placed_by_insert:
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
                add("Switch to 'Style' tab.")
                for s in style_parts:
                    add(s)

        # After all charts in this row, set section style to stretch
        if len(row_viz_indices) > 1:
            add_procedure("set_section_style_stretch")

    # === Footer: creation timestamp text box ===
    created_on = datetime.now().strftime("%m/%d/%Y")
    footer_text = f"Looker Studio Agent created the dashboard on {created_on}"
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
    parser.add_argument("--phased", action="store_true", help="Show phased output instead of flat")
    args = parser.parse_args()

    if args.phased:
        result = compile_config_phased(args.config)
        print(f"Vertex AI Project: {result['vertex_ai_project_id']}")
        print(f"Total phases: {len(result['phases'])}\n")
        for i, phase in enumerate(result["phases"]):
            print(f"{'=' * 60}")
            print(f"Phase {i + 1}: {phase['name']}  ({len(phase['steps'])} steps)")
            print(f"  {phase['description']}")
            print(f"{'=' * 60}")
            print(phase["task_string"])
            print()
    else:
        result = compile_config(args.config)
        print(f"Vertex AI Project: {result['vertex_ai_project_id']}")
        print("=" * 60)
        print(result["task_string"])
        print("=" * 60)
