# Playbook Adjustment — Session Progress

> Dates: 2026-04-07 → 2026-04-08
> Branch: `subagent_workload`
> Total changes: +788 / -372 lines across 4 files + 1 new file

---

## Objectives

1. Merge all chart-creation row phases into a single phase for compaction resilience
2. Consolidate the playbook to be **commodity** (chart-type agnostic)
3. Extract live aria-labels for playbook reference
4. Diagnose and fix failures from live agent run (axis titles, speed)
5. **Build custom controller actions to eliminate agent hallucination under context pressure**
6. **Add compaction-resilient memory (todo.md rules header)**

---

## Phase 1: Playbook Consolidation (Apr 7)

### 1.1 `scripts/task_compiler.py` — Single Chart Creation Phase

**Before**: Each responsive row was a separate phase (Phase 3, 4, 5…), each spawning its own agent.
**After**: All rows merged into a single "Chart Creation" phase with row separator headers.

Key changes:
- New `compile_config_phased()` replaces `compile_config()` — returns `{"phases": [...], ...}`
- Added `generate_todo()` and `update_todo_phase()` for progress tracking via `todo.md`
- Row headers (`--- ROW 1 of 2: chart_a, chart_b ---`) survive message compaction
- Footer step + report title appended to same Chart Creation phase
- Constraints (aliases, data limits, style constraints) now loaded from playbook JSON — single source of truth
- Extracted `_compile_viz_steps()` helper for per-visualization step compilation
- Added calculated fields verification step at end of each batch

### 1.2 `scripts/looker_studio_playbook.json` — Commodity Playbook

**Before**: Some procedures referenced chart-specific section names (e.g., "Series section").
**After**: All procedures use generic, chart-type-agnostic instructions.

Key changes:
- **Moved constraints into playbook**: `chart_canonical_aliases`, `chart_data_limits`, `chart_style_constraints`
- **Index-based disambiguation**: `querySelectorAll` index `[0]` = dimension axis, `[1]` = metric axis
- **`style_set_color`**: Changed from "Series section" to "find the first color swatch"
- **`style_toggle_compact_numbers`**: Check Setup tab first, then Style tab

### 1.3 `scripts/test_vision_click_action.py` — Phased Orchestrator

**Before**: Single agent, single task, no phase handoff.
**After**: Multi-phase orchestrator with per-phase agent instances and URL handoff.

- Tiered system prompts (`SYSTEM_PROMPT_FLASH` / `SYSTEM_PROMPT_PRO`)
- Dual-model: flash (gemini-3-flash-preview) for setup, pro (gemini-3.1-pro-preview) for charts
- `max_actions_per_step=1`, `message_compaction=True`
- Phase handoff via `result.history[-1].state.url`

### 1.4 `scripts/looker_studio_aria_labels.md` — New Reference

Extracted 157 aria-labels from live Looker Studio, organized into 19 UI sections with duplicate label disambiguation table and Style tab section order.

---

## Phase 2: Live Run Diagnosis (Apr 7–8)

Analyzed 169-step conversation log from `phase_3_Chart_Creation`.

### Failure Patterns Found

| # | Pattern | Steps Wasted | Streak |
|---|---|---|---|
| 1 | `target_label_name` search fails in field picker | 12+ | 3, 4, 5 consecutive |
| 2 | "Add section" (+) button not found | 7 | 7 consecutive |
| 3 | `Show title` toggle not found (off-screen) | 6+ | 3 consecutive |
| 4 | Metric chip opens field picker instead of edit panel | 5+ | 2 consecutive |

**Root causes**:
1. Field picker virtual scroll + broken search input interaction
2. Hover-triggered button not in DOM until mouseover event
3. Post-compaction: agent forgets `scrollIntoView` rule, uses `scroll` action instead
4. Chip text click vs aggregation icon click — agent confuses which opens what

### Compaction Effect Confirmed

After step ~60, the agent stopped using `evaluate()` with `scrollIntoView` for Style tab elements. It fell back to the generic `scroll` browser-use action, which doesn't work on the property panel's internal scrollbar. The system prompt rules were effectively lost after compaction summarized the agent's history.

---

## Phase 3: Custom Controller Actions (Apr 8)

### 3.1 New file: `scripts/looker_studio_actions.py`

9 deterministic controller actions registered on the browser-use Controller. Each replaces an unreliable LLM-driven multi-step interaction with a single JS call via CDP.

| Action | What it does | Failure it eliminates |
|---|---|---|
| `search_field_picker(field_name)` | Finds the picker search input in overlays, clears it, types field name using native setter, waits for virtual scroll filter, clicks the match | Field picker search returning "No results" (12+ wasted steps) |
| `add_section()` | Finds add-section button via class, falls back to hover-reveal + proximity search | "+" button not found (7 wasted steps) |
| `add_chart_in_section(section_index)` | Clicks placeholder or add-chart button in target section | Placeholder vs populated section confusion |
| `set_chart_title(title_text)` | Scrolls to Show title toggle, enables it, types title via native setter | Toggle not visible after compaction forgets scrollIntoView |
| `enable_axis_title(axis)` | Enables Show axes if needed, then scrolls to + enables Show axis title[0 or 1] | Axis titles never enabled (stale DOM + off-screen) |
| `set_aggregation(aggregation_type)` | Opens aggregation dropdown, selects option from mat-option list | Chip text vs aggregation icon confusion |
| `set_section_stretch(section_index)` | Opens style menu + clicks Stretch in one call | Two-step interaction reduced to one |
| `enable_shadow()` | Scrolls to + idempotently enables Add border shadow toggle | Off-screen toggle |
| `enable_data_labels()` | Scrolls to + idempotently enables Show data labels toggle | Off-screen toggle |

**Key design patterns**:
- All actions use `scrollIntoView({block:'center'})` before interacting
- All toggles check `classList.contains('mdc-switch--checked')` for idempotency
- Text inputs use `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` for Angular compatibility
- Promise-based with timeouts for DOM settling (200–500ms)
- All return structured JSON `{ok: bool, ...}` parsed by `_run_js()` helper

### 3.2 Playbook Updated — Action Reference Format

All procedures now use consistent format:
```
Use action "<action_name>" to <purpose>, with <param>=<value>.
```

Examples from compiled output:
```
2. Use action "add_chart_in_section" to open the chart picker, with section_index=1.
5. Use action "search_field_picker" to find and select the field, with field_name='bin_roam_count_10m'.
7. Use action "set_chart_title" to enable the title and set its text, with title_text='Roam Count (10m)'.
8. Use action "enable_axis_title" to enable the dimension axis title, with axis='x'.
```

### 3.3 System Prompt Updated

`SYSTEM_PROMPT_PRO` now includes a **custom actions catalog** listing all 9 actions with descriptions. This is in the system prompt (never compacted), so the agent always knows these tools exist.

### 3.4 todo.md Rules Header

`generate_todo()` now injects a rules cheat sheet at the top of todo.md:
```markdown
# Rules (always follow)
- When a step says "Use <action_name>", call that custom action directly — do NOT try to do it manually.
- Use search_field_picker to select fields — do NOT type into the picker search box manually.
- Use add_section to add new sections — do NOT try to find the '+' button.
...
```
This is shown in `<todo_contents>` every step — survives all compaction.

### 3.5 Calculated Fields Verification

Added a verification step at the end of each Calculated Fields phase:
```
Verification: Read the Data panel and confirm these calculated fields exist: 'field_a', 'field_b'.
If any field is missing, use the same 'Add a field' approach to create it.
```

---

## Files Changed

| File | Status | Lines |
|---|---|---|
| `scripts/looker_studio_actions.py` | **New** | +320 |
| `scripts/task_compiler.py` | Modified | +480 / -80 |
| `scripts/looker_studio_playbook.json` | Modified | +347 / -282 |
| `scripts/test_vision_click_action.py` | Modified | +302 / -283 |
| `scripts/looker_studio_aria_labels.md` | New (from prior session) | +298 |

---

## Projected Impact

Based on the 169-step run analysis:
- **72 steps** were pure retry/failure loops from the 4 fixed patterns
- Custom actions should reduce the run to **~90–100 steps**
- `search_field_picker` alone eliminates ~12 wasted steps per run
- `add_section` eliminates 7 wasted steps per section addition
- Style tab actions (`set_chart_title`, `enable_axis_title`) eliminate 6+ steps per chart

---

## Compaction Resilience Summary

Three layers protect the agent from forgetting rules:

| Layer | What survives | Content |
|---|---|---|
| **System prompt** | Always (never compacted) | Custom actions catalog, execution rules |
| **todo.md header** | Always (shown every step via `<todo_contents>`) | Rules cheat sheet: which actions to use |
| **Custom actions** | N/A (deterministic JS) | Agent doesn't need to remember HOW — just calls the action |

---

## Remaining / Future Work

- [ ] Verify custom actions in a live run
- [ ] Monitor step count reduction (target: 169 → <100)
- [ ] Assess if `max_actions_per_step` can be increased now that risky steps are deterministic
- [ ] Consider sub-agent per chart if single-phase compaction still causes drift
- [ ] Add more custom actions for remaining manual procedures (color picker, filter dialogs)
