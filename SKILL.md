---
name: looker-studio-automation
description: Automates the design and creation of Looker Studio dashboards. Use this when the user wants to build a Looker Studio dashboard interactively, OR when the user provides a pre-configured JSON file and wants it executed directly without questioning.
---

# Looker Studio Automation

## Core Rules
- Ask ONE question at a time. Never hallucinate Project IDs, metrics, or dimensions.
- Interactive mode config file: `./.looker-automation/dashboard_config.json`. CLI mode: use the absolute path provided by the user.
- Always Read config file before Write (preserve existing data).
- **Never write raw user words into config.** All values must be translated first.
- `chart_color` must always be a hex code (e.g. `"#FF6D00"`), never a color name.
- `layout_instructions` must always be exact vision_click position descriptions, never words like "side by side".

##  HelperScript
```bash
SCRIPT_DIR=".claude/skills/looker-studio-automation/scripts"
bash "$SCRIPT_DIR/config_helper.sh" init              # Creates dir + empty config
bash "$SCRIPT_DIR/config_helper.sh" status            # Outputs RESUME_FROM=step1|step2|step4|complete
bash "$SCRIPT_DIR/config_helper.sh" validate          # Outputs VALID or MISSING: field field2 (presence-only check)
# Note: full validation (formats, enums, counts) runs automatically inside run.sh via validate_config.py
```

## JSON Schema
```json
{
  "vertex_ai_project_id": "",
  "data_source": { "project_id": "", "dataset": "", "table_name": "" },
  "visualizations": [
    { "chart_type": "", "metrics": [], "dimensions": [], "title": "",
      "special_configurations": { "font_size": "", "chart_color": "", "background_color": "", "show_x_axis_title": false, "show_y_axis_title": false, "add_shadow": false, "legend_position": "", "show_data_labels": false, "compact_numbers": false, "other": "" } }
  ],
  "layout_instructions": []
}
```

## Workflow

### Step 1: Init & Data Source
**If the user's message contains a `.json` file path: extract it, resolve to absolute path (`realpath`), then skip to Step 5 and execute. `run.sh` validates automatically — if invalid, report the errors and ask the user to fix them.**
1. Run `config_helper.sh init`. If EXISTS, run `config_helper.sh status` and resume from the indicated step.
2. If `RESUME_FROM=complete`: offer "Execute now" or "Start fresh".
3. Ask for Vertex AI Project ID, then BigQuery Project ID / Dataset / Table. Write to config.

### Step 2: Visualizations

**Collect one chart at a time**

  1. Ask use what would they like to see/present, and suggest chart type using **Interence rules** if they are not explicity give a chart type. 
  **Inference rules:**

  | User says | Infer | Then ask |
  |-----------|-------|----------|
  | "trends / over time" | Line chart, time dimension | Granularity (daily/monthly/quarterly)? |
  | "compare / breakdown by" | Bar chart | What to compare? |
  | "total / overall" | Scorecard | — |
  | "by region / country" | Geo chart | — |
  | "same thing but for X" | Reuse previous metric, change dimension | — |
  | "show data" / "performance" | Too vague | Which aspect — totals, trends, comparisons? |

  2. Collect `chart_type`, title, metrics, dimensions, special_configurations from user. Append to `visualizations` array and Write after each.
  
  **special_configurations rules**
  - Consolidate user's requirements to chart's configuration and get confirmation before write to `special_configurations`
  | User says | Traslate to |
  |-----------|-------|
  | "color" | hex code|
  | "enable label, effect, or title" | True or False |
  | "label position" | direction |
  | "font size" | number |
  | "others" | Infer user intent and ask again |

### Step 3: Confirm Visualizations
Present summary. If rejected, ask what to change (data source / specific chart / add more) and loop back.

### Step 4: Layout
Collect the relative position of each chart's 
1. Ask User: 
  1. `where to put the chart`
  - A `anchor point` - white canvas, chart, label, etc. 
  - A `position` - Position(must be a direction) - top, top-left, bottom, bottom-right, etc.
  2. `gap with anchor chart`
  - Have a gap with the `anchor point` or not
  
2. Construct Answer to a sentence
- start off with the words : "Flush to the `position`"
  - If gap is needed, add `with 10px gap`
- then refer the `anchor point`, if `anchor point` is a label or a chart, add `outer boudart box` in the suffix
**Example**

| Anchor point | Gap | Position | Construct to |
|-------|-------|-------|---------|
| "white canvas" | No | top left | Flush to the top-left of the white canvas |
| "bar chart at the top-left" | Yes | bottom right | Flush to the bottom-right of the top-left chart with 10px gap|

3. One entry per chart, in the same order as `visualizations`, record the construction to `layout_instructions`

### Step 5: Final Confirmation & Execute
Present complete plan. If rejected, route to relevant step.
When approved:
1. Execute: `bash .claude/skills/looker-studio-automation/scripts/run.sh --config /absolute/path/to/dashboard_config.json`
   `run.sh` validates the config automatically as its first step. If invalid, report the errors and loop back to the relevant step.

**If execution fails:**
- "ADC missing" / "authentication" → guide user to run `gcloud auth application-default login`
- "table not found" → verify BigQuery resource names
- "vision_click failed" → refine layout instructions (Step 4)