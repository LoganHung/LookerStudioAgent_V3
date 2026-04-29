# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LookerStudioAgent v3 automates Google Looker Studio dashboard creation via browser automation. A declarative JSON config describes the dashboard (data source, charts, layout); the system compiles it into phased browser tasks executed by AI agents (Gemini via browser-use framework).

## Architecture

### Execution Pipeline

```
dashboard_config.json
  → validate_config.py (schema check)
  → task_compiler.py (compile_config_phased → phases with task text + model tier)
  → test_vision_click_action.py (orchestrator: launches Chrome, runs agent per phase)
    → browser-use Agent reads DOM, follows compiled task steps, updates todo.md
```

### Three-Phase Execution

Phases exist to manage agent token/memory limits. Each phase gets its own browser-use Agent instance:

1. **Setup** (flash model): Create blank report, connect BigQuery data source
2. **Calculated Fields** (flash): Add derived fields (max ~10 per phase, splits if more)
3. **Chart Creation** (pro model): One phase per responsive row — adds section, places charts, configures dimensions/metrics/styling

### Prompt-Only Design

No custom JavaScript actions. The system prompt (`scripts/looker_studio_system_prompt.md`) teaches HOW to operate Looker Studio (field picker, toggle handling, Style tab scrolling). Playbook procedures (`scripts/looker_studio_playbook.json`) describe WHAT to do in natural language. The agent identifies elements by `aria-label`, `role`, and visible text — never by CSS class selectors.

### Key Design Decisions

- **`override_system_message`** is used for the pro agent (replaces browser-use default prompt entirely). This means any browser-use output schema changes require manual sync — see `looker_studio_system_prompt.md` `<output>` section.
- **`extend_system_message`** is used for the flash agent (appends to browser-use default). Safer across package updates.
- **`Controller(exclude_actions=["evaluate"])`** prevents the agent from running arbitrary JS.
- **`placed_by_insert` flag** in task_compiler: when `row_idx > 1`, the Insert toolbar auto-creates a section + places the first chart, so `add_first_chart_to_section` is skipped.
- **Responsive layout only**: 12-column grid, sections stack vertically. `responsive_rows: [[0,1],[2,3]]` means chart indices 0,1 share row 1; 2,3 share row 2.

## Playbook JSON Structure

`scripts/looker_studio_playbook.json` is the single source of truth for:
- `chart_canonical_aliases`: normalizes user input ("column" → "bar")
- `chart_data_limits`: max metrics/dimensions per chart type
- `chart_style_constraints`: valid style options per chart type
- `chart_type_labels`: exact UI label used in Looker Studio menus
- `procedures`: natural-language steps the task compiler expands into task text

## browser-use Internals

The browser-use package is at `/home/datateam/.browser-use-env/lib/python3.12/site-packages/browser_use/`. Key files:

- `agent/system_prompts/system_prompt.md` — default system prompt (replaced by override for pro agent)
- `agent/prompts.py` — `AgentMessagePrompt.get_user_message()` builds the state message sent each step with `<agent_history>`, `<agent_state>`, `<browser_state>` tags
- `agent/message_manager/service.py` — message compaction logic (triggers every 25 steps when history > 40k chars)
- `dom/views.py` — `DEFAULT_INCLUDE_ATTRIBUTES` controls which DOM attributes the agent can see (class is excluded)

**Agent cannot see CSS classes in the DOM tree.** Only `aria-label`, `role`, `id`, `title`, `name`, visible text, and highlight indices are serialized. Class selectors only work inside `evaluate()` JS (which is disabled).

## Known Issues

- **Compaction step-jumping**: After message compaction (~step 25+), the agent may misinterpret which step it's on and skip ahead. Root cause: compacted history summary (max 6000 chars) doesn't reliably preserve step progress. Mitigation: phased execution keeps each phase short.
- **Override prompt drift**: When browser-use is updated, the override system prompt's `<output>` JSON schema may fall out of sync with what browser-use expects. Check `agent/views.py` for `AgentOutput` / `AgentOutputFlashMode` Pydantic models after updates.
