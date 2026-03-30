# Looker Studio Chart Reference

Source: Google Cloud official documentation (verified March 2026)

## Chart Type → Data Constraints

| Chart Type | Max Metrics | Max Dimensions | Notes |
|---|---|---|---|
| scorecard | 1 | 0-1 (optional comparison) | Dimension optional, used for comparison only |
| bar, column, stacked_bar, stacked_column, 100_stacked_bar, 100_stacked_column | 20 | 2 | Breakdown dimension as 2nd dim |
| line, combo | 5 | 1 + optional breakdown | Time or category dimension |
| time_series, sparkline | 5 | 1 (time) + optional breakdown | Time dimension required |
| area, stacked_area, 100_stacked_area | 5 | 1 + optional breakdown | |
| pie, donut | 1 | 1 | Single metric, single dimension |
| waterfall | 1 | 1 | |
| scatter, bubble | 2-3 (X, Y, optional size) | 1-3 | Bubble = scatter + size metric |
| geo, google_maps | 1 (color) + optional | 1 (geo field) | Geo dimension required |
| gauge | 1 | 0 | Optional target/ranges, no dimension |
| bullet | 1 | 0 | Optional target + ranges |
| funnel | 1 | 1 | |
| treemap | 1-2 (size + optional color) | 1-2 (hierarchy) | |
| table | unlimited | unlimited | Supports pagination, sorting |
| pivot_table | unlimited | row dims + column dims | No metric filters allowed |
| dropdown_list, fixed_size_list | 0 | 0 | Uses control_field |
| checkbox | 0 | 0 | Uses control_field (boolean) |

## Chart Type → Valid `special_configurations`

Legend for our config field names:
- `font_size` — primary text/metric font size
- `chart_color` — series/metric color (hex)
- `background_color` — chart container background (hex)
- `show_x_axis_title` — X-axis label visibility
- `show_y_axis_title` — Y-axis label visibility
- `add_shadow` — border shadow on container
- `legend_position` — legend placement (top/down/right/left)
- `show_data_labels` — display values on data points/bars
- `compact_numbers` — abbreviate large numbers (553K)
- `cross_filtering` — chart acts as filter control
- `others` — free-form for unlisted options

| Chart Type | font_size | chart_color | background_color | show_x_axis_title | show_y_axis_title | add_shadow | legend_position | show_data_labels | compact_numbers | cross_filtering |
|---|---|---|---|---|---|---|---|---|---|---|
| scorecard | Y | Y | Y | - | - | Y | - | - | Y | - |
| bar, column (all variants) | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| line, combo | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| time_series, sparkline | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| area (all variants) | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| pie, donut | Y | Y | Y | - | - | Y | Y | Y | - | Y |
| waterfall | Y | Y | Y | Y | Y | Y | - | Y | Y | Y |
| scatter, bubble | Y | Y | Y | Y | Y | Y | Y | - | - | Y |
| geo, google_maps | - | Y | Y | - | - | Y | Y | - | - | Y |
| gauge | Y | Y | Y | - | - | Y | - | - | Y | - |
| bullet | Y | Y | Y | - | - | Y | - | Y | Y | - |
| funnel | Y | Y | Y | - | - | Y | Y | Y | Y | Y |
| treemap | Y | Y | Y | - | - | Y | Y | - | - | Y |
| table | Y | - | Y | - | - | Y | - | - | Y | Y |
| pivot_table | Y | - | Y | - | - | Y | - | - | Y | - |
| dropdown_list, fixed_size_list | Y | - | Y | - | - | Y | - | - | - | - |
| checkbox | Y | - | Y | - | - | Y | - | - | - | - |

`Y` = valid, `-` = not applicable (will be skipped by compiler)

## Chart-Specific Style Options NOT in Our Schema

These exist in Looker Studio but are not mapped to `special_configurations` fields.
Use the `others` field for these if needed.

| Chart Type | Additional Style Options |
|---|---|
| scorecard | compact_numbers, decimal_precision, comparison_positive_color, comparison_negative_color, progress_visual (bar/circle/none) |
| bar/column | bar_width, group_bar_width, reference_lines, conditional_formatting, zoom |
| line/time_series | line_weight, line_style, gradient, cumulative, show_points, stepped_lines, smooth, trendline, missing_data_mode, reference_lines, zoom |
| area | missing_data_mode, reference_lines, zoom |
| pie/donut | slice_label_type (none/percentage/label/value), slice_padding, donut_hole_size |
| waterfall | rising_bar_color, falling_bar_color, total_bar_color, labels_position (inside/outside) |
| scatter | trendline (linear/polynomial/exponential), max 1000 bubbles |
| geo | zoom_area, map_colors (color scale) |
| gauge | min/max values, target, ranges (up to 5) |
| funnel | bar_label_position (inside/outside), sort order |
| treemap | levels_to_show, color_by (metric/dimension) |
| table | row_numbers, auto_height, wrap_text, horizontal_scrolling, header_background_color, conditional_formatting |
| pivot_table | totals, subtotals, conditional_formatting |

## Sources

- [Types of charts in Looker Studio](https://docs.cloud.google.com/looker/docs/studio/types-of-charts-in-looker-studio)
- [Scorecard reference](https://docs.cloud.google.com/looker/docs/studio/scorecard-reference)
- [Bar chart and column chart reference](https://docs.cloud.google.com/looker/docs/studio/bar-chart-and-column-chart-reference)
- [Time series reference](https://docs.cloud.google.com/looker/docs/studio/time-series-reference)
- [Line chart and combo chart reference](https://support.google.com/looker-studio/answer/7398001)
- [Pie chart reference](https://docs.cloud.google.com/looker/docs/studio/pie-chart-reference)
- [Area chart reference](https://docs.cloud.google.com/looker/docs/studio/area-chart-reference)
- [Waterfall chart reference](https://docs.cloud.google.com/looker/docs/studio/waterfall-chart-reference)
- [Scatter chart reference](https://docs.cloud.google.com/looker/docs/studio/scatter-chart-reference)
- [Geo chart reference](https://docs.cloud.google.com/looker/docs/studio/geo-chart-reference)
- [Google Maps reference](https://docs.cloud.google.com/looker/docs/studio/google-maps-reference)
- [Gauge chart reference](https://cloud.google.com/looker/docs/studio/gauge-chart-reference)
- [Funnel chart reference](https://docs.cloud.google.com/looker/docs/studio/funnel-chart-reference)
- [Treemap reference](https://cloud.google.com/looker/docs/studio/treemap-reference)
- [Table reference](https://cloud.google.com/looker/docs/studio/table-reference)
- [Pivot table reference](https://docs.cloud.google.com/looker/docs/studio/pivot-table-reference)
- [Drop-down list and Fixed-size list control](https://docs.cloud.google.com/looker/docs/studio/drop-down-list-and-fixed-size-list-control)
- [Checkbox control](https://docs.cloud.google.com/looker/docs/studio/checkbox-control)
