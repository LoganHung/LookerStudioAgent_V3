"""
Looker Studio Automation - Responsive Layout with Browser-Use
"""
import asyncio
import logging
import sys
import os
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
for lib in ["httpx", "httpcore", "urllib3", "playwright"]:
    logging.getLogger(lib).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

from browser_use import Agent, Browser, Controller
from browser_use import ChatGoogle
from looker_studio_actions import register_looker_actions


# =============================================================================
# CONTROLLER with custom Looker Studio actions
# =============================================================================
def create_controller() -> Controller:
    controller = Controller()
    register_looker_actions(controller)
    logger.info("Controller created with Looker Studio actions")
    return controller


# =============================================================================
# TASK COMPILER
# =============================================================================
from task_compiler import compile_config_phased, generate_todo, update_todo_phase


# =============================================================================
# CHROME LAUNCHER
# =============================================================================
def launch_chrome_linux(user_data_dir: str):
    chrome_candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium"
    ]
    chrome_path = next((c for c in chrome_candidates if os.path.exists(c)), None)
    if not chrome_path:
        raise FileNotFoundError("Chrome/Chromium not found")

    # Kill any existing Chrome using port 9222
    kill_result = subprocess.run(
        ["pkill", "-f", "remote-debugging-port=9222"],
        capture_output=True
    )
    if kill_result.returncode == 0:
        logger.info("Killed existing Chrome on port 9222")
        time.sleep(2)

    # Remove stale lock files
    for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        try:
            os.remove(os.path.join(user_data_dir, lock_file))
            logger.info(f"Removed stale lock: {lock_file}")
        except FileNotFoundError:
            pass

    cmd = [
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--profile-directory=Default",
        "--window-size=1920,1080",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--headless=NEW"
    ]

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info(f"Chrome launched with CDP on port 9222")
    logger.info(f"   Chrome path: {chrome_path}")
    logger.info(f"   User data: {user_data_dir}")


# =============================================================================
# SYSTEM PROMPTS (per model tier)
# =============================================================================
SYSTEM_PROMPT_FLASH = """
Looker Studio operating rules:

- Be concise. use muti-sequence actions when you know the exact button to click to finish the task.
- Do exactly the task instruct, follow the order of the task.
- Do not click toolbar buttons except to add a text box.
- Do not pretent you know all the button's position, read the DOM tree then interact with the website.
"""

SYSTEM_PROMPT_PRO = """
Looker Studio operating rules:

Core execution:
    DO: 
    - Complete each step fully before moving to the next.
    - Be concise. use muti-sequence actions when you know the exact button to click to finish the task.
    - Do exactly the task instruct, follow the order of the task.
    - For dropdowns and pickers, wait for options to load before selecting.
    - For text fields, click the field, clear existing text, then type the new value.
    - If an action has no effect or fail after 2 attempts, press 'Escape' first. If still no effect, click at a non-function area.
    - When a task step says "Use <action_name>", call that custom action directly — do NOT try to do it manually.

    Don't
    - Do not type field or metric names into the Data panel search bar (far right). Use the Setup tab chip interactions only.
    - Do not pretend you know all the button's position, read the DOM tree then interact with the website.
    - Do not click any toolbar buttons except to add a text box.

Field picker:
- Clicking a field chip opens either a field picker (scrollable list) or an edit panel (form with aggregation dropdown).
- If an edit panel opens and you need the field picker, press Escape and click the chip's text label instead.
"""


def build_phase_task(
    phase: dict, phase_idx: int, current_url: str | None = None,
) -> str:
    """Build the task string for a phase agent, including context preamble."""
    lines = []

    # If we have the URL from the previous phase, tell the agent to go there
    if current_url and phase_idx > 0:
        lines.append(f"The report is open at: {current_url}")
        lines.append("Navigate to this URL first if you are not already on it.")
        lines.append("")
    elif phase_idx == 0:
        lines.append("The browser is open. Start from scratch.")
        lines.append("")

    lines.append(phase["task_string"])
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================
async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Looker Studio Automation — Phased Orchestrator")
    parser.add_argument("--config", type=str, required=True, help="Path to dashboard_config.json")
    args = parser.parse_args()

    print(f"\nReading configuration from: {args.config}\n")

    compiled = compile_config_phased(args.config)
    phases = compiled["phases"]
    vertex_ai_project_id = compiled["vertex_ai_project_id"]
    user_data_dir = compiled["user_data_dir"]
    skipped_configs = compiled.get("skipped_configs", [])

    # Conversation logs directory (next to the config file)
    config_dir = os.path.dirname(os.path.abspath(args.config))
    conversation_log_dir = os.path.join(config_dir, "conversation_logs")
    os.makedirs(conversation_log_dir, exist_ok=True)
    print(f"Conversation logs: {conversation_log_dir}")

    if not vertex_ai_project_id:
        print("[ERROR] vertex_ai_project_id is required in the config file")
        return
    if not user_data_dir:
        print("[ERROR] user_data_dir is missing from config. Run: bash config_helper.sh set_user_data_dir")
        return

    # Generate todo.md upfront with ALL phases and steps
    todo_path = os.path.join(os.path.dirname(os.path.abspath(args.config)), "todo.md")
    generate_todo(phases, todo_path)
    print(f"Todo written to: {todo_path}")

    print(f"\nVertex AI Project ID: {vertex_ai_project_id}")
    print(f"Total phases: {len(phases)}")
    for i, phase in enumerate(phases):
        print(f"  Phase {i + 1}: {phase['name']} — {len(phase['steps'])} steps")
    print()

    project = vertex_ai_project_id
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

    llm_flash = ChatGoogle(
        model="gemini-3-flash-preview",
        project=project, location=location, vertexai=True,
        temperature=0.5, thinking_level="minimal",
    )
    llm_pro = ChatGoogle(
        model="gemini-3-flash-preview",
        project=project, location=location, vertexai=True,
        temperature=0.5, thinking_level="low",
    )

    launch_chrome_linux(user_data_dir)
    await asyncio.sleep(10)

    CDP_URL = "http://127.0.0.1:9222"

    completed_phases: list[dict] = []
    current_url: str | None = None
    current_phase = 0

    try:
        for phase_idx, phase in enumerate(phases):
            current_phase = phase_idx
            print("\n" + "=" * 80)
            print(f"PHASE {phase_idx + 1}/{len(phases)}: {phase['name']}")
            print(f"  {phase['description']}")
            print(f"  Steps: {len(phase['steps'])}")
            print("=" * 80 + "\n")

            task = build_phase_task(phase, phase_idx, current_url)

            # Select model tier for this phase
            model_tier = phase.get("model_tier", "flash")
            print(f"  Model tier: {model_tier} ({'gemini-3.1-pro-preview' if model_tier == 'pro' else 'gemini-3-flash-preview'})")

            # Fresh browser connection per phase — Chrome stays alive,
            # but browser-use gets a clean session to avoid stale event handlers.
            browser = Browser(
                cdp_url=CDP_URL,
                disable_security=True,
                wait_between_actions=0.5,
                minimum_wait_page_load_time=0.5,
            )

            phase_log_dir = os.path.join(conversation_log_dir, f"phase_{phase_idx + 1}_{phase['name'].replace(' ', '_')}")
            flash_agent = Agent(
                task=task,
                llm=llm_flash,
                browser=browser,
                # controller=create_controller(),
                llm_timeout=100,
                use_vision=False,
                extend_system_message=SYSTEM_PROMPT_FLASH,
                flash_mode=False,
                message_compaction=True,
            )
            pro_agent = Agent(
                task=task,
                llm=llm_pro,
                browser=browser,
                controller=create_controller(),
                use_vision=False,
                extend_system_message=SYSTEM_PROMPT_PRO,
                flash_mode=False,
                use_thinking=True,
                enable_planning=True,
                message_compaction=True,
            )

            agent = flash_agent if model_tier == 'flash' else pro_agent

            result = await agent.run()

            # Extract the final URL from agent history for next phase handoff
            try:
                if result and result.history:
                    current_url = result.history[-1].state.url
                    logger.info(f"Captured URL for next phase: {current_url}")
            except Exception as e:
                logger.warning(f"Could not capture URL after phase {phase_idx + 1}: {e}")

            # Check if the agent actually finished or stopped early
            if result and not result.is_done():
                errors = [e for e in result.errors() if e]
                if errors:
                    print(f"\n[WARNING] Phase {phase_idx + 1} had errors: {errors}")
                else:
                    print(f"\n[WARNING] Phase {phase_idx + 1} may not have completed fully")

            # Save structured history for this phase
            history_path = os.path.join(phase_log_dir, "agent_history.json")
            agent.save_history(history_path)
            logger.info(f"Agent history saved to {history_path}")

            update_todo_phase(todo_path, phase)
            completed_phases.append(phase)
            print(f"\n[✓] Phase {phase_idx + 1} complete — todo.md updated")
            if current_url:
                print(f"    URL: {current_url}")
            print()

            # Pause between phases to let browser settle
            if phase_idx < len(phases) - 1:
                await asyncio.sleep(5)

        print("\n" + "=" * 80)
        print("[SUCCESS] ALL PHASES COMPLETED")
        print("=" * 80)

        if skipped_configs:
            print("\n[Config Filter Report — the following were auto-skipped]")
            for msg in skipped_configs:
                print(f"  ⚠ {msg}")
            print()

    except Exception as e:
        print(f"\n[ERROR] Phase {current_phase + 1} failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Kill Chrome to clean up
        subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
        logger.info("Chrome process cleaned up")

if __name__ == "__main__":
    asyncio.run(main())
