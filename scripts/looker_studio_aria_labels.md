# Looker Studio — aria-label Reference (Bar Chart, Edit Mode)

> Extracted from a live Looker Studio responsive-layout report in edit mode.
> Source: CDP port 9222, `document.querySelectorAll('[aria-label]')` + role/section analysis.
> Date: 2026-04-07

---

## 1. Top Navigation Bar

| aria-label | Tag | Notes |
|---|---|---|
| `Return to home page` | `<button>` | Looker Studio logo/home button |
| `Rename` | `<div>` | id=`ng2-editable-label`, shows report title text |
| `Refresh data` | `<button>` | Hidden by default |
| `Label for button that lets users share a report with other people` | `<button>` | "Share" button |
| `More options` | `<button>` | Dropdown arrow (x2 — appears on multiple toolbar items) |
| `More report actions` | `<button>` | id=`more-options-header-menu-button`, kebab menu |
| `Open the user account switcher panel.` | `<button>` | Google account switcher |

## 2. Edit Toolbar

| aria-label | Tag | Notes |
|---|---|---|
| `Undo` | `<button>` | |
| `Redo` | `<button>` | |
| `Selection Mode` | `<button>` | |
| `Zoom` | `<button>` | Toolbar zoom (not chart zoom toggle) |
| `Add page` | `<button>` | |
| `Add data` | `<button>` | |
| `Blend` | `<button>` | |
| `Add a chart` | `<button>` | **Toolbar** "Add a chart" — opens chart picker. Same label as section-level button |
| `Community visualizations and components` | `<button>` | |
| `Add a control` | `<button>` | |
| `URL Embed` | `<button>` | |
| `Image` | `<button>` | |
| `Text` | `<button>` | Text box toolbar button |
| `Shape` | `<button>` | |
| `Theme and layout` | `<button>` | Opens theme/layout panel |
| `More` | `<button>` | Hidden overflow menu |

## 3. Filter Bar

| aria-label | Tag | Notes |
|---|---|---|
| `Filters applied to the report` | `<mat-chip-listbox>` | Container |
| `Add quick filter` | `<button>` | Text shows "Add filter" |
| `Reset filters` | `<button>` | Text shows "Reset" |
| `Opens a menu with more options when clicked` | `<button>` | id=`filter-header-kebab` |

## 4. Canvas — Section Controls

| aria-label | Tag | Notes |
|---|---|---|
| `Add a chart` | `<button>` | **Section-level** — appears on populated section edge. Same label as toolbar button |
| `add a control` | `<button>` | Section-level control button (lowercase "a") |
| `Open style menu` | `<button>` | Section style/alignment menu |
| `Add chart in placeholder` | N/A | Empty section center button (not visible on current page — sections already populated) |

### Section Style Menu (inside `Open style menu`)

| aria-label | Tag | Notes |
|---|---|---|
| `Stretch` | `<button>` | Horizontal alignment — stretch charts to fill |
| `Left` | `<button>` | Horizontal alignment — left-align |
| `Center` | `<button>` | Horizontal alignment — center |
| `Right` | `<button>` | Horizontal alignment — right |

## 5. Canvas — Chart Components

| aria-label | Tag | Notes |
|---|---|---|
| `Press enter or space to show chart header` | `<div>` | Wraps each chart/component. Includes report title, date picker, charts |
| `Show properties` | `<button>` | Chart header button — opens property panel for that chart |
| `Sort` | `<button>` | Chart header sort button |
| `Show BigQuery job details` | `<button>` | Chart header — BigQuery info |
| `Show chart menu` | `<button>` | Chart header kebab menu |
| `getDateText()` | `<button>` | Date range picker button (text: "Select date range") |

## 6. Property Panel — Tabs

| aria-label | Tag | Role | Notes |
|---|---|---|---|
| (none) | `<div>` | `tab` | Text content: **"Setup"** — matched by visible text |
| (none) | `<div>` | `tab` | Text content: **"Style"** — matched by visible text |
| (none) | `<div>` | `tablist` | Contains both tabs |

## 7. Setup Tab — Toggles (role="switch")

| aria-label | Default State | Notes |
|---|---|---|
| `Drill down` | OFF | |
| `Optional metrics` | OFF | |
| `Metric sliders` | OFF | |
| `Cross-filtering` | OFF | |
| `Change sorting` | ON | Enables sort controls below |
| `Zoom` | OFF | Chart-level zoom |

## 8. Setup Tab — Radio Buttons

| aria-label | Type | Notes |
|---|---|---|
| `radio button: Descending` | `<input type="radio">` | Sort order (primary) |
| `radio button: Ascending` | `<input type="radio">` | Sort order (primary) |
| `radio button: Descending` | `<input type="radio">` | Sort order (secondary) |
| `radio button: Ascending` | `<input type="radio">` | Sort order (secondary) |

## 9. Setup Tab — Chips (Dimension/Metric)

Tags: `<ng2-concept-chip>` wrapping `<common-chip>`

| Location | Visible Text | Notes |
|---|---|---|
| Dimension - Y axis | `bin_roaming_acceleration` | Click chip text (span) to open field picker |
| Breakdown dimension | `target_label_name` | |
| Metric - X axis | `entity_id` | Click chip text to open field picker or edit panel |
| Sort (primary) | `entity_id` | |
| Sort (secondary) | `entity_id` | |

**Important**: Chips have no `aria-label`. Agent must click the visible text span inside the chip.

## 10. Style Tab — Chart Title Section

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Show title` | `<button role="switch">` | toggle | Enables title input |
| `textinput` | `<input>` | text | Title text field (visible after toggle ON) |
| `Font family` | `<mat-select>` | combobox | Title font dropdown |
| `Font size` | `<mat-select>` | combobox | Title font size dropdown |

## 11. Style Tab — Bar Chart Section

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Vertical` | `<button role="radio">` | toggle | Bar orientation |
| `Horizontal` | `<button role="radio">` | toggle | Bar orientation |
| `Bars` | `<input type="number">` | numeric | Number of bars |
| `increment value` | `<button>` | action | +/- buttons for numeric fields (many instances) |
| `decrement value` | `<button>` | action | +/- buttons for numeric fields (many instances) |
| `Group the rest as "Others"` | `<button role="switch">` | toggle | x2 — one for dimension, one for series |
| `Bar width` | `<input type="range">` | slider | |
| `Group bar width` | `<input type="range">` | slider | |
| `Stacked bars` | `<button role="switch">` | toggle | |
| `Show data labels` | `<button role="switch">` | toggle | |
| `radio button: Single color` | `<input type="radio">` | radio | Color mode |
| `radio button: Bar order` | `<input type="radio">` | radio | Color mode |
| `radio button: Dimension values` | `<input type="radio">` | radio | Color mode |

### Color Swatches

| aria-label | Tag | Notes |
|---|---|---|
| `color: #4285f4` | `<span>` | Series color swatch (click to change) |
| `color: #f59e52` | `<span>` | Series 2 color |
| `color: #ad7fe6` | `<span>` | Series 3 color |
| ... | `<span>` | Up to 20 series swatches |

## 12. Style Tab — Axes Section

**Parent toggle**: `Show axes` must be ON for axis controls to appear.

### Bottom X-Axis (dimension axis)

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Show axes` | `<button role="switch">` | toggle | **Prerequisite** — enables all axis controls |
| `Reverse Y-axis direction` | `<button role="switch">` | toggle | |
| `Reverse X-axis direction` | `<button role="switch">` | toggle | |
| `Align both axes to 0` | `<button role="switch">` | toggle | |
| `Show axis title` | `<button role="switch">` | toggle | **First instance** — Bottom X-Axis title |
| `Show axis labels` | `<button role="switch">` | toggle | First instance — X-Axis labels |
| `Font family` | `<mat-select>` | combobox | X-Axis label font |
| `Font size` | `<input type="number">` | numeric | X-Axis label size |
| `Rotation (0° to 90°)` | `<input type="number">` | numeric | X-Axis label rotation |
| `Show axis line` | `<button role="switch">` | toggle | First instance — X-Axis line |

### Y-Axis (metric axis)

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Axis min` | `<input type="number">` | numeric | Y-Axis minimum |
| `Axis max` | `<input type="number">` | numeric | Y-Axis maximum |
| `Custom tick interval` | `<input type="number">` | numeric | Y-Axis tick spacing |
| `Log scale` | `<button role="switch">` | toggle | Y-Axis log scale |
| `Show axis title` | `<button role="switch">` | toggle | **Second instance** — Y-Axis title |
| `Show axis labels` | `<button role="switch">` | toggle | Second instance — Y-Axis labels |
| `Font family` | `<mat-select>` | combobox | Y-Axis label font |
| `Font size` | `<input type="number">` | numeric | Y-Axis label size |
| `Rotation (0° to 90°)` | `<input type="number">` | numeric | Y-Axis label rotation |
| `Show axis line` | `<button role="switch">` | toggle | Second instance — Y-Axis line |

> **Disambiguation**: `Show axis title` appears **twice** — first for Bottom X-Axis, second for Y-Axis. The Style tab content order is: Chart title > Bar chart > Axes > Bottom X-Axis > Y-Axis > Grid > Legend > Background. Agent must scroll the property panel to reach the correct instance.

## 13. Style Tab — Grid Section

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Show left Y-axis gridlines` | `<button role="switch">` | toggle | |
| `Show X-axis gridlines` | `<button role="switch">` | toggle | |
| `Grid line style` | `<mat-select>` | combobox | Solid/Dashed/Dotted |

## 14. Style Tab — Legend Section

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Display legend` | `<button role="switch">` | toggle | |
| `Position` | `<mat-select>` | combobox | Top/Bottom/Left/Right |
| `Alignment` | `<mat-select>` | combobox | Left/Center/Right |
| `Align legend with grid` | `<button role="switch">` | toggle | |
| `Max lines` | `<input type="number">` | numeric | |
| `Font family` | `<mat-select>` | combobox | |
| `Font size` | `<mat-select>` | combobox | |

## 15. Style Tab — Background and Border

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Opacity` | `<mat-select>` | combobox | 0-100% |
| `Border radius` | `<mat-select>` | combobox | px |
| `Border weight` | `<mat-select>` | combobox | None/1px/2px/... |
| `Border style` | `<mat-select>` | combobox | Solid/Dashed/Dotted |
| `Add border shadow` | `<button role="switch">` | toggle | |

## 16. Style Tab — Chart Header

| aria-label | Tag | Type | Notes |
|---|---|---|---|
| `Chart header` | `<mat-select>` | combobox | Show on hover / Always show / Do not show |

## 17. Data Panel (far right)

| aria-label | Tag | Notes |
|---|---|---|
| `Data` | `<span role="heading">` | Panel header |
| `Text box to search Looker Studio` | `<input type="search">` | **DO NOT type field names here** — use Setup tab chips |
| `Edit or fix data source` | `<div>` | Edit pencil icon (sometimes hidden) |
| `Help page for blends` | `<ng2-help-button>` | Blend help link |
| `Add a field` | `<button>` | Opens calculated field / add field dialog |
| `Add a parameter` | `<button>` | |
| `Add data` | `<button>` | Text: "Add Data" |

## 18. Panel Toggle Buttons (bottom of right panel)

| aria-label | Tag | Text | Notes |
|---|---|---|---|
| `Toggle panel` | `<button>` | "Data" | Show/hide Data panel |
| `Toggle panel` | `<button>` | "Properties" | Show/hide Properties panel |
| `Toggle panel` | `<button>` | "Filter bar" | Show/hide Filter bar |
| `Toggle panel` | `<button>` | `keyboard_arrow_right` | Collapse/expand panels (FAB button) |

## 19. Chart Picker (expansion panel)

| aria-label | Tag | Role | Notes |
|---|---|---|---|
| (none) | `<mat-expansion-panel-header>` | `button` | Text: "Chart types 49" — expandable chart type picker |

---

## Style Tab Section Order (Bar Chart)

The Style tab renders sections in this order (top to bottom). Sections below the fold require scrolling the property panel.

1. **Chart title** — `Show title`, title text input, font controls
2. **Bar chart** — orientation, bars count, bar width, stacked, data labels
3. **Series** — color swatches, color mode radio buttons
4. **Reference lines** — "Add a reference line" / "Add a reference band"
5. **Axes** — `Show axes` (prerequisite toggle)
6. **Bottom X-Axis** — `Show axis title`, `Show axis labels`, font, rotation, `Show axis line`
7. **Y-Axis** — `Axis min/max`, `Custom tick interval`, `Log scale`, `Show axis title`, `Show axis labels`, font, rotation, `Show axis line`
8. **Grid** — background, border, gridlines, grid line style
9. **Legend** — `Display legend`, position, alignment, font
10. **Background and border** — background color, opacity, border, `Add border shadow`
11. **Chart header** — visibility dropdown

---

## Duplicate aria-label Summary

These labels appear multiple times on the page. Agent must use context (position, section, surrounding text) to disambiguate:

| aria-label | Count | Disambiguation |
|---|---|---|
| `Add a chart` | 3 | 1x toolbar, 1x per populated section |
| `add a control` | 2 | 1x toolbar (capitalized), 1x per section (lowercase) |
| `More options` | 2 | Toolbar dropdown arrows |
| `Open style menu` | 1 per section | One per responsive section |
| `Show axis title` | 2 | First = Bottom X-Axis, Second = Y-Axis |
| `Show axis labels` | 2 | First = Bottom X-Axis, Second = Y-Axis |
| `Show axis line` | 2 | First = Bottom X-Axis, Second = Y-Axis |
| `Font family` | 4 | Title, X-Axis, Y-Axis, Legend |
| `Font size` | 4+ | Title, X-Axis, Y-Axis, Legend, Bar count |
| `increment value` | 7+ | One per numeric input field |
| `decrement value` | 7+ | One per numeric input field |
| `Group the rest as "Others"` | 2 | Dimension grouping, Series grouping |
| `Toggle panel` | 4 | Differentiated by visible text: Data/Properties/Filter bar/arrow |
| `Text box to search Looker Studio` | 2 | One in Properties panel header, one in Data panel |
| `Press enter or space to show chart header` | N | One per chart/component on canvas |
| `color: #xxxxxx` | 20 | One per series color swatch |
