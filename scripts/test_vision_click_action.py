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
from browser_use.browser import BrowserSession
from browser_use.agent.views import ActionResult
from playwright.async_api import Browser as PlaywrightBrowser, Page, async_playwright
from pydantic import BaseModel, Field


# =============================================================================
# PLAYWRIGHT STATE
# =============================================================================
_playwright_instance = None
_playwright_browser: PlaywrightBrowser | None = None


async def connect_playwright_to_cdp(cdp_url: str = "http://127.0.0.1:9222"):
    global _playwright_instance, _playwright_browser
    _playwright_instance = await async_playwright().start()
    _playwright_browser = await _playwright_instance.chromium.connect_over_cdp(cdp_url)
    logger.info(f"Playwright connected to CDP at {cdp_url}")


async def _get_active_page() -> Page | None:
    """Resolve the active Looker Studio page at call time across all CDP contexts."""
    if _playwright_browser is None:
        return None
    looker_hosts = ("datastudio.google.com", "lookerstudio.google.com")
    for context in _playwright_browser.contexts:
        for page in context.pages:
            if any(h in page.url for h in looker_hosts):
                return page
    for context in reversed(_playwright_browser.contexts):
        if context.pages:
            return context.pages[-1]
    return None


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

- Carefully read through the DOM tree before taking action — find the right element using a Region of Interest mindset. This reduces errors significantly.
- Use muti-sequence actions when you know the exact button to click to finish the task.
- Identify elements by aria-label, role, or visible text. Do not guess positions.
- Do exactly the task instruct, follow the order of the task.
- Do not click toolbar buttons except to add a text box.
- Do not pretent you know all the button's position, read the DOM tree then interact with the website.
- If an unintended popup or panel opened, press Escape or click the white canvas area to dismiss it.
"""

SYSTEM_PROMPT = """
You are operating Google Looker Studio in edit mode to build a dashboard — create charts, configure data fields, apply styles, and manage layout.

<action_rules>
- Action 'hover_and_click_revealed' is allowed only when specified in the task, otherwise use `click`.
- No chain step can be taken after using 'hover_and_click_revealed'.
- Shadow DOM elements with `[index]` markers are directly clickable with `click(index)`. Do NOT use `evaluate`.
</action_rules>

<looker_studio_rules>
DOM Navigation:
- When adding a chart to an existing section, always use the section-level 'Add a chart' button or the 'Add Chart' placeholder — never use the toolbar 'Insert' menu (that is only for new sections or a text box).
- Do not click or type anything in the Data panel (the panel listing all data fields).

Scroll:
- Looker Studio is Angular-based; normal pagedown/scroll commands won't affect the Style panel, field lists, etc.

Field Picker (set/change/add a dimension or metric):
1. Click the chip showing the current field (or "Add dimension"/"Add metric"). A new `*[N]` popup with a row list must appear. If the list is empty, press Escape and restart.
2. Read the rows in the popup. If the target field's row is visible, click it and skip to step 4. (Rows are field names, often prefixed with an ABC/123/calendar icon. Section headings like "DIMENSIONS" or "Calculated fields" are not rows.)
3. If the target row is not visible (large field list with virtual scrolling), type the field name to filter, then click the matching row.
- If the list is still empty, promptly sendkey 'Escape', restart the task again.

Dimension and Metric Chips:
- To REPLACE an existing dimension/metric: click the chip's text label to open the field picker. Do NOT click "Add dimension" / "Add metric".
- To ADD a new dimension/metric: click "Add dimension" / "Add metric".
- Metric chip has two clickable zones — text label (opens field picker) vs. icon area (opens aggregation edit panel). Choose based on intent.
- To change aggregation: click the metric chip's icon area to open the edit panel, then select from the aggregation dropdown.

Style Tab:
- The Style tab panel has its own internal scrollbar, separate from the page.
- To reach off-screen Style tab elements, click inside the Style panel first, then use send_keys ArrowDown or PageDown until the target is visible.

Toggle Switches:
- Before clicking a toggle, check its `aria-checked` attribute in the DOM. Only click if the state needs to change.
- Some toggles are hidden until their parent toggle is enabled. Enable the parent first if the child is not visible:
  - "Show axis title" requires "Show axes" to be ON first.
  - Title text input requires "Show title" to be ON first.
- Duplicate aria-labels exist (e.g. "Show axis title" for X and Y axis). The first occurrence in the DOM tree is X-axis, the second is Y-axis. Use the `[index]` number to click the correct one.

Report Title:
- Double-click the report title text to enter edit mode. Single-click does not work.
- After double-click, use Ctrl+A to select all, then type the new title.

Recovery:
- If stuck after 2 attempts, press Escape or click an empty canvas area, check the browser state, then retry.
- If an unintended popup or panel opened, press Escape or click the white canvas area to dismiss it.
</looker_studio_rules>
"""

# =============================================================================
# CONTROLLER + PLAYWRIGHT HOVER ACTIONS
# =============================================================================
class HoverAndClickRevealedAction(BaseModel):
    hover_index: int = Field(..., description='Browser-use index [N] of the element to hover (e.g. the chart inside the section)')
    button_aria_label: str = Field(..., description="aria-label of the button to click after hover, e.g. 'Add a chart'")
    # wait_ms: int = Field(default=2000, description='Milliseconds to wait after hover for buttons to appear before clicking')


_controller = Controller(exclude_actions=["evaluate"])


@_controller.registry.action(
    "Atomically hover over an indexed element AND mouse-click a hover-revealed button by aria-label, "
    "in a single action so the hover state stays active. Uses raw mouse coordinates (page.mouse.click) "
    "to avoid Playwright actionability checks that time out on hover-conditional buttons. "
    "Picks the button whose Y-center falls within the hovered element's row. "
    "Use for section action buttons like 'Add a chart' or 'add a control'.",
    param_model=HoverAndClickRevealedAction,
)
async def hover_and_click_revealed(
    params: HoverAndClickRevealedAction, browser_session: BrowserSession
) -> ActionResult:
    page = await _get_active_page()
    if page is None:
        return ActionResult(error="Playwright: no active page found.")
    try:
        selector_map = await browser_session.get_selector_map()
        if params.hover_index not in selector_map:
            return ActionResult(error=f"No element with index [{params.hover_index}] in selector_map")
        node = selector_map[params.hover_index]
        if node.absolute_position is None:
            return ActionResult(error=f"Element [{params.hover_index}] has no bounding box")
        hbox = node.absolute_position
        hover_x = hbox.x + hbox.width / 2
        hover_y = hbox.y + hbox.height / 2

        await page.mouse.move(hover_x, hover_y)
        await page.wait_for_timeout(2000)

        buttons = page.get_by_label(params.button_aria_label, exact=True)
        count = await buttons.count()
        if count == 0:
            return ActionResult(error=f"No buttons with aria-label='{params.button_aria_label}' in DOM after hover")

        target_box = None
        target_idx = -1
        all_centers = []
        for i in range(count):
            try:
                box = await buttons.nth(i).bounding_box()
            except Exception:
                box = None
            if box is None:
                all_centers.append(None)
                continue
            cy = box['y'] + box['height'] / 2
            all_centers.append(round(cy))
            if target_box is None and hbox.y <= cy <= hbox.y + hbox.height:
                target_box = box
                target_idx = i

        if target_box is None:
            return ActionResult(
                error=(
                    f"No '{params.button_aria_label}' button found in row of [{params.hover_index}] "
                    f"(y∈[{hbox.y:.0f},{hbox.y + hbox.height:.0f}]). "
                    f"Found {count} buttons, Y-centers: {all_centers}. Hover may not have revealed them."
                )
            )

        btn_x = target_box['x'] + target_box['width'] / 2
        btn_y = target_box['y'] + target_box['height'] / 2
        await page.mouse.click(btn_x, btn_y)

        return ActionResult(
            extracted_content=(
                f"Hovered [{params.hover_index}] at ({hover_x:.0f},{hover_y:.0f}), "
                f"mouse-clicked '{params.button_aria_label}' at ({btn_x:.0f},{btn_y:.0f}) "
                f"(button {target_idx + 1}/{count}, all Y-centers: {all_centers})"
            )
        )
    except Exception as e:
        return ActionResult(error=f"hover_and_click_revealed failed: {e}")


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
    await connect_playwright_to_cdp(CDP_URL)

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
                headless=True
            )

            phase_log_dir = os.path.join(conversation_log_dir, f"phase_{phase_idx + 1}_{phase['name'].replace(' ', '_')}")
            
            flash_agent = Agent(
                task=task,
                llm=llm_flash,
                browser=browser,
                controller=_controller,
                llm_timeout=100,
                use_vision=False,
                max_history_items=10,
                include_attributes=[                                                                                                   
                    "aria-label", "title", 
                    "role", "type",
                     "name", "id", "value",                                                      
                    "placeholder", "aria-checked", "checked", "aria-expanded",                                                         
                    "aria-selected", "data-state", "alt",                                                                              
                ],
                extend_system_message=SYSTEM_PROMPT_FLASH,
                flash_mode=False,
                message_compaction=True,
            )

            pro_agent = Agent(
                task=task,
                llm=llm_flash,
                browser=browser,
                controller=_controller,
                use_vision=False,
                extend_system_message=SYSTEM_PROMPT,
                include_attributes=[                                                                                                   
                    "aria-label", "title", 
                    "role", "type", 
                    "name", "id", "value",                                                      
                    "placeholder", "aria-checked", "checked", "aria-expanded",                                                         
                    "aria-selected", "data-state", "alt",                                                                              
                ],    
                max_history_items=10,
                flash_mode=False,
                use_thinking=True,
                message_compaction=True
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
        if _playwright_browser:
            await _playwright_browser.close()
        if _playwright_instance:
            await _playwright_instance.stop()
        # Kill Chrome to clean up
        subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
        logger.info("Chrome process cleaned up")

if __name__ == "__main__":
    asyncio.run(main())