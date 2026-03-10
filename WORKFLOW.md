# WORKFLOW.md describe the Agent Skill work flow in a nutshell
 - This is a new feature to allow using bash scripts to activate the Skill.
# Workflow Mode 
**Interactive Mode**
 - the skill will be load when user ask e.g. "Please help me to build the dashboard."
 - The rest of the workflow will be adhere to `SKILL.md`
**Command Line Mode**
 - a command will be given e.g. `cat data.json | claude "請根據這個 JSON 幫我做出 Looker Studio Dashboard" --yes`
 - Same as Interactive mode, the Skill will be loaded, but it will directly execute:
   ```bash
   bash .claude/skills/looker-studio-automation/scripts/run.sh --config data.json
   ```
    **Execution**
    `run.sh` sets up the environment and runs the automation. The Python venv is anchored to the skill directory (`SKILL_DIR`), resolved via `readlink -f` on the script itself — independent of where `run.sh` is called from or where the config file lives.
    Error scenarios to handle:
    - Chart type not available → return error, ask user to update `chart_type` in config
    - Visual configuration not supported → return error, ask user to fix the relevant `special_configurations` field