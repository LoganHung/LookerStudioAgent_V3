---
name: looker-studio-automation
description: Automates the design and creation of Looker Studio dashboards. Use this when the user wants to build a Looker Studio dashboard.
---

## Core Rules
- Ask ONE question at a time if user not specify any requirements. Never hallucinate Project IDs, metrics, or dimensions.
- Should not assume the data is clean and ready to use. Ask the user the explictiy meaning of the metric and dimension .
- Store requirement in config file: `./.looker-automation/dashboard_config.json`if not provied by user.
- Always Read config file before Write (preserve existing data).
- Configure charts with only their available options in Google Looker Studio. Do not make up configurations that do not exist. Invalid configs and excess metrics/dimensions are auto-filtered during compilation — the dashboard still builds, skipped items are reported after completion.
- **Never write raw user words into config.** All values must be translated first.

## JSON Schema
```json
{
  "vertex_ai_project_id": "",
  "data_source": { "project_id": "", "dataset": "", "table_name": "" },
  "calculated_fields": [
    { "field_name": "", "formula": "" }
  ],
  "report_title": "",
  "responsive_rows": [[0, 1, 2], [3, 4, 5, 6]],
  "visualizations": [
    { "chart_type": "", "metrics": [{"name": "", "aggregation": "SUM|AVG|COUNT|COUNT_DISTINCT|MIN|MAX"}], "dimensions": [], "title": "",
      "filters": [
        { "type": "include|exclude", "field": "", "condition": "", "value": "" }
      ],
      "control_field": "",
      "special_configurations": { "font_size": "","font_color": "",  "chart_color": "", "background_color": "", "show_x_axis_title": false, "show_y_axis_title": false, "add_shadow": false, "legend_position": "", "show_data_labels": false, "compact_numbers": false, "cross_filtering": false, "others": "" } }
  ]
}
```
**Optional fields:** `filters`, `control_field`, `cross_filtering` — omit if not needed. For metrics without aggregation, use a plain string instead of an object: `"metrics": ["field_name"]`.

**Derived value rule:** If the metrics/dimensions is the default in the dataset, put into the `calculated_fields` with `field_name` and `formula` in the config json file. Also, the `metrics` name should be aligned with `field_name`

**Responsive layout rule:** `responsive_rows` is an array of arrays. Each inner array contains the indices (0-based) of visualizations that should appear side-by-side in the same row/section. Charts in the same row are automatically stretched to fill the section evenly. Every visualization index must appear exactly once.

## Workflow

### Step 1: Init & Data Source

**If the user's message contains a `.json` file path: extract it, resolve to absolute path (`realpath`), skip to step 4 then execute — if invalid, report the errors and ask the user to fix them.**
**If the user's message explicitly mentions project id (vertexAI and GCP), data source(table and dataset), chart's specification(type, style, layout), transfer to JSON requirement, then go to step 4 and execute.**

1. Run `scripts/config_helper.sh init`. If return EXISTS, run `scripts/config_helper.sh status` and resume from the indicated step.
2. If `RESUME_FROM=complete`: offer "Execute now" or "Start fresh".
3. Ask for Vertex AI Project ID, then BigQuery Project ID / Dataset / Table. Write to config.

### Step 2: Visualizations

**Collect one chart at a time**

1. Ask user what they would like to see/present, and suggest chart type using **Inference rules** if not explicitly given.

   | User says | Infer | Then ask |
   |-----------|-------|----------|
   | "trends / over time" | Line chart, time dimension | Granularity (daily/monthly/quarterly)? |
   | "compare / breakdown by" | Bar chart | What to compare? |
   | "total / overall" | Scorecard | — |
   | "by region / country" | Geo chart | — |
   | "same thing but for X" | Reuse previous metric, change dimension | — |
   | "show data" / "performance" | Too vague | Which aspect — totals, trends, comparisons? |
   | "filter by X" / "dropdown for X" | Dropdown control, `control_field` = X | — |
   | "checkbox for X" | Checkbox control, `control_field` = X | — |
   | "only show where X = Y" | Chart-level filter (include) | — |
   | "exclude X" | Chart-level filter (exclude) | — |

2. Collect `chart_type`, title, metrics, dimensions, special_configurations from user. Append to `visualizations` array and Write after each.

  - Consolidate user's requirements to chart's configuration and get confirmation before write to `special_configurations`.
  - Ask explicit question to confirm the requirement, e.g. font color is fuzzy without knowing its `chart` or `font` color.

   | User says | Translate to config field |
   |-----------|--------------------------|
   | "a dropdown / list to filter by X" | `chart_type: dropdown_list`, `control_field: X` |
   | "a checkbox for X" | `chart_type: checkbox`, `control_field: X` |
   | "only show where X equals Y" | `filters: [{ type: include, field: X, condition: equals, value: Y }]` |
   | "exclude / hide X = Y" | `filters: [{ type: exclude, field: X, condition: equals, value: Y }]` |
   | "where X contains / starts with / is greater than Y" | map to `condition`: `contains` / `starts_with` / `greater_than` |
   | "average / count / max of X" | `metrics: [{"name": "X", "aggregation": "AVG|COUNT|MAX"}]` (valid: SUM, AVG, COUNT, COUNT DISTINCT, MIN, MAX) |
   | "color" | hex code |
   | "enable label, effect, or title" | boolean `true` / `false` |
   | "font size" | number |

>**Only when the user requests specific style details out of JSON schema** (e.g. trendline, donut hole size, reference lines, slice labels): read `reference.md` to verify the option exists for that chart type before writing to config.

### Step 3: Layout (Responsive Rows)

Collect how charts should be grouped into rows/sections.

1. Ask user how they want charts arranged, e.g.:
   - "3 scorecards in the first row, then a full-width line chart below"
   - "put charts 1-3 side by side, chart 4 on its own row"

2. Translate to `responsive_rows` — an array of arrays of visualization indices:
   - Example: 7 visualizations → `[[0, 1, 2], [3, 4, 5], [6]]`
   - Each inner array = one section/row
   - Charts in the same row are evenly stretched

3. Write `responsive_rows` to config.

### Step 4: Final Confirmation & Execute

Present complete plan. If rejected, route to relevant step. If approved, execute:
```bash
bash .claude/skills/looker-studio-automation/scripts/run.sh --config /absolute/path/to/dashboard_config.json
```
Use`run.sh` validates the config automatically as its first step. If error occurs, run `scripts/config_helper.sh validate` and report the errors and loop back to the relevant step.

**If execution fails:**
- "ADC missing" / "authentication" → guide user to run `gcloud auth application-default login`
- "table not found" → verify BigQuery resource names