"""
Manual test — hardcoded task to validate playbook + system prompt (no task_compiler).

Usage:
    python test_manual_task.py
"""
import asyncio
import logging
import subprocess
import sys
import os
import time
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
for lib in ["httpx", "httpcore", "urllib3", "playwright"]:
    logging.getLogger(lib).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


from browser_use import Agent, Browser, Controller
from browser_use.browser import BrowserSession
from browser_use.llm.google import ChatGoogle
from browser_use.agent.views import ActionResult
from dataclasses import dataclass
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
    # Fallback: last page in the most recent context
    for context in reversed(_playwright_browser.contexts):
        if context.pages:
            return context.pages[-1]
    return None


# =============================================================================
# CHROME LAUNCHER
# =============================================================================
def launch_chrome(user_data_dir: str = "/home/datateam/demo_roamingDashboard/chrome-profile"):
    chrome_candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium"
    ]
    chrome_path = next((c for c in chrome_candidates if os.path.exists(c)), None)
    if not chrome_path:
        raise FileNotFoundError("Chrome/Chromium not found")

    subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
    time.sleep(2)

    for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        try:
            os.remove(os.path.join(user_data_dir, lock))
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
        # "--headless=new",
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info(f"Chrome launched: {chrome_path} | CDP port 9222 | user-data: {user_data_dir}")


# =============================================================================
# SYSTEM PROMPT
# =============================================================================
SYSTEM_PROMPT = """
As an AI agent, your mission is to operate Google Looker Studio in edit mode to create charts, configure data fields, apply styles, and manage report layout. Follow task steps precisely and complete each fully before the next.

**Follow the best practice to complete the task you are asked to do with Google Looker Studio operation**

<browser_state_format>
Interactive elements appear as indexed tree nodes:
[33]<div />
	[35]<input type=text placeholder=Enter name />
	*[38]<button aria-label=Submit />
		Submit
- Only `[index]` elements are interactive. Indentation = parent/child.
- `*[` = new elements since last step (caused by your previous action). Inspect them — they may be dropdowns, popups, or results triggered by your last action.
- Pure text without `[]` is not interactive.
- `|SCROLL|` prefix indicates scrollable containers with scroll position info
- `|SHADOW(open)|` or `|SHADOW(closed)|` prefix indicates shadow DOM elements
</browser_state_format>

<action_rules>
- Always verify the previous action's result before proceeding.
- Use multi-action sequences to complete the task when you are sure all action items are visible in the DOM.
- Safe to chain: `input` + `input`, `input` + `click`, `scroll` + `scroll`.
- Do NOT chain actions that both change the page (e.g. `click` + `navigate`).

**Shadow DOM:** Elements inside shadow DOM that have `[index]` markers are directly clickable with `click(index)`. Do NOT use `evaluate` to click them.
</action_rules>

<looker_studio_rules>
Must follow best practices to complete tasks effectively and efficiently

DOM Navigation:
- Carefully read through the DOM before taking any actions.
- Identify elements by aria-label, role, or visible text. Do not guess positions.
- When adding a chart to an existing section, always use the section-level 'Add a chart' button or the 'Add Chart' placeholder inside the section.
- Never click 'Add a chart' button at the tool bar. The toolbar 'Insert' menu is only for creating new sections with a chart or adding a text box.
- Do not click or type anything in the Data panel (the panel listing all data fields).

Scroll: 
- Looker Studio is written by Angular, normal pagedown, scroll commnad wont effect to the style panel, field lists, and etc.

Field Picker:
- When the field picker opens, scroll through the list to find the target field and click it.
- If the field is not visible, type the field name into the search input to filter results, then click the match.
- If typing does not filter results, clear the input and scroll the list manually instead.

Dimension and Metric Chips:
- To REPLACE an existing dimension/metric: click the chip's text label to open the field picker. Do NOT click "Add dimension" / "Add metric".
- To ADD a new dimension/metric: click "Add dimension" / "Add metric".
- Metric chip has two clickable zones — text label (opens field picker) vs. icon area (opens aggregation edit panel). Choose based on intent.
- To change aggregation: click the metric chip's icon area to open the edit panel, then select from the aggregation dropdown.

Style Tab:
- The Style tab panel has its own internal scrollbar, separate from the page.
- Carefully read through the function 'Style', if the task mentioned items not appear, click the synonym first.
- To reach off-screen Style tab elements, click inside the Style panel first, then use send_keys with ArrowDown or PageDown until the target element is visible.

Toggle Switches:
- Before clicking a toggle, check its `aria-checked` attribute in the DOM. Only click if the state needs to change.
- Some toggles are hidden until their parent toggle is enabled. Enable the parent first if the child is not visible:
  - "Show axis title" requires "Show axes" to be ON first.
  - Title text input requires "Show title" to be ON first.
- Duplicate aria-labels exist (e.g. "Show axis title" for X and Y axis). The first occurrence in the DOM tree is X-axis, the second is Y-axis. Use the `[index]` number to click the correct one.

Sections:
- If the section is not empty, click either the Add chart or the Add control button on the right edge of the section. These buttons appear when you hover over a section. 
- Each section is a `<div class="section-container">` with no aria-label. Its children include section-level buttons ("Add a chart", "Open style menu", "add a control").
- To select a section (i.e. "click at the border of the section"): click the `<div class="section-container">` element itself — not any child chart wrapper or button inside it. This is what "clicking the border" means in DOM terms.
- IMPORTANT: The FIRST section-container always contains the report title text box (class contains "simple-description") and a date picker (class contains "simple-daterangepicker"). Never click this section when adding charts — it is the header row.

Report Title:
- Double-click the report title text to enter edit mode. Single-click does not work.
- After double-click, use Ctrl+A to select all, then type the new title.

Recovery:
- If stuck after 2 attempts, press Escape or click an empty area of the canvas, check the browser state, and then retry the ongoing task.
- If an unintended popup or panel opened, press Escape or click the white canvas area to dismiss it.
</looker_studio_rules>

<verify>
After each action, verify the result by reading the current DOM tree — do NOT assume success from memory alone.
Confirm the intended change actually took effect: the field appeared, the toggle enabled, the chart added, the text updated, the section created. If not, retry before moving on.
</verify>
"""

_prompt_path = os.path.join(os.path.dirname(__file__), "looker_studio_system_prompt.md")
with open(_prompt_path, "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT_PRO = _f.read()

# =============================================================================
# TASK
# =============================================================================
REPORT_URL = "https://datastudio.google.com/reporting/61507d3d-7873-4e58-a7c7-a18faef99828/page/XyZwF/edit"

TASK = f"""
Follow the step order to complete the task
Navigate to: {REPORT_URL}
Wait for the page to fully load before starting.

# - First Row
0. Click at the panel toggle'Data' at the right of the webpage.
1. Click at the 'Add Chart' placeholder and select 'bar chart'. 
2. In the Setup tab, change the default dimension to 'bin_roam_count_10m'.
3. In the Setup tab, click 'Add dimension' and click 'target_label_name' as dimension.
4. In the Setup tab, change the default metric to 'entity_id', and then change the aggregation method to 'COUNT'. After that sendkey: Escape
5. Switch to 'Style' tab.
6. Enable the 'Show title' toggle if off, then set the chart title to 'Roam Count (10m) — Where Do At-Risk Devices Concentrate?'.
7. Scroll to 'Show axes' and enable it if off. Then scroll to the FIRST 'Show axis title' toggle (X-axis) and enable it if off.
8. Scroll to the SECOND 'Show axis title' toggle (Y-axis) and enable it if off.
9.  Find the bar chart you just configured in the DOM tree (its [N] index). Call hover_by_index with that index. Then check if 'Add a chart' button is now visible in the DOM — if yes, click it and select 'bar chart'. If not visible, call hover_and_click_revealed with the same index and button_aria_label='Add a chart', then select 'bar chart'.
10. In the Setup tab, change the default dimension to 'bin_roam_count_10m'.
11. In the Setup tab, click 'Add dimension' and click 'target_label_name' as dimension.
12. In the Setup tab, change the default metric to 'entity_id', and then change the aggregation method to 'COUNT'. After that sendkey: Escape
13. Switch to 'Style' tab.
14. Scroll to 'Show axes' and enable it if off. Then scroll to the FIRST 'Show axis title' toggle (X-axis) and enable it if off.
15. Scroll to the SECOND 'Show axis title' toggle (Y-axis) and enable it if off.
16. Find the most recently configured chart in the DOM tree (its [N] index). Call hover_by_index with that index. Then check if 'Add a chart' button is now visible in the DOM — if yes, click it and select 'bar chart'. If not visible, call hover_and_click_revealed with the same index and button_aria_label='Add a chart', then select 'bar chart'.
17. Find the visualization you just configured in the DOM tree (its [N] index). Call hover_and_click_revealed with the same index and button_aria_label='Open style menu', then select 'stretch'.

"""
# # - Second Row
# 17. Click Insert in the toolbar and select 'pie chart'
# 18. In the Setup tab, change the default dimension to 'bin_roam_count_10m'.
# 19. In the Setup tab, click 'Add dimension' and click 'target_label_name' as dimension.
# 20. In the Setup tab, change the default metric to 'entity_id', and then change the aggregation method to 'COUNT'. After that sendkey: Escape
# 21. Switch to 'Style' tab.
# 22. Enable the 'Show title' toggle if off, then set the chart title to 'Roam Count (10m) — Where Do At-Risk Devices Concentrate?'.
# 23. Scroll to 'Show axes' and enable it if off. Then scroll to the FIRST 'Show axis title' toggle (X-axis) and enable it if off.
# 24. Scroll to the SECOND 'Show axis title' toggle (Y-axis) and enable it if off.
# 25. Find the bar chart you just configured in the DOM tree (its [N] index). Call hover_and_click_revealed with hover_index=[N] and button_aria_label='Add a chart'. This hovers the chart and clicks the section's revealed 'Add a chart' button in one atomic action. Then select 'bar chart' from the menu that appears.
# 26. In the Setup tab, change the default dimension to 'bin_roam_count_10m'.
# 27. In the Setup tab, click 'Add dimension' and click 'target_label_name' as dimension.
# 28. In the Setup tab, change the default metric to 'entity_id', and then change the aggregation method to 'COUNT'. After that sendkey: Escape
# 29. Switch to 'Style' tab.
# 30. Scroll to 'Show axes' and enable it if off. Then scroll to the FIRST 'Show axis title' toggle (X-axis) and enable it if off.
# 31. Scroll to the SECOND 'Show axis title' toggle (Y-axis) and enable it if off.
# 32. Find the bar chart you just configured in the DOM tree (its [N] index). Call hover_and_click_revealed with hover_index=[N] and button_aria_label='Add a chart'. This hovers the chart and clicks the section's revealed 'Add a chart' button in one atomic action. Then select 'bar chart' from the menu that appears.

# 9.  Find the bar chart you just configured in the DOM tree (its [N] index). Call hover_and_click_revealed with hover_index=[N] and button_aria_label='Add a chart'. This hovers the chart and clicks the section's revealed 'Add a chart' button in one atomic action. Then select 'bar chart' from the menu that appears.
# 10. In the Setup tab, change the default dimension to 'bin_roaming_acceleration'.


# =============================================================================
# CONTROLLER + PLAYWRIGHT HOVER ACTIONS
# =============================================================================
controller = Controller()
controller.set_coordinate_clicking(True)
controller.exclude_action('evaluate')
controller.exclude_action('scroll')


class HoverBySelectorAction(BaseModel):
    selector: str = Field(..., description='CSS selector of the element to hover (supports class selectors like .section-container)')
    nth: int = Field(default=0, description='0-based index when multiple elements match. Use -1 to target the last match.')


class HoverByCoordinatesAction(BaseModel):
    x: float = Field(..., description='X pixel coordinate on the page to hover')
    y: float = Field(..., description='Y pixel coordinate on the page to hover')


class HoverByIndexAction(BaseModel):
    index: int = Field(..., description='Browser-use element index [N] shown in the DOM tree')


class HoverAndClickRevealedAction(BaseModel):
    hover_index: int = Field(..., description='Browser-use index [N] of the element to hover (e.g. the chart inside the section)')
    button_aria_label: str = Field(..., description="aria-label of the button to click after hover, e.g. 'Add a chart'")
    wait_ms: int = Field(default=1000, description='Milliseconds to wait after hover for buttons to appear before clicking')


@controller.registry.action(
    "Hover over a DOM element using a CSS selector. Supports class selectors (.section-container) "
    "and attribute selectors. Use this to reveal hover-triggered UI elements such as section action buttons. "
    "Set nth=-1 to target the last matching element.",
    param_model=HoverBySelectorAction,
)
async def hover_by_selector(params: HoverBySelectorAction) -> ActionResult:
    page = await _get_active_page()
    if page is None:
        return ActionResult(error="Playwright: no active page found. Cannot hover.")
    try:
        base = page.locator(params.selector)
        count = await base.count()
        if count == 0:
            return ActionResult(error=f"hover_by_selector: no elements found for '{params.selector}' on {page.url}")
        locator = base.last() if params.nth == -1 else base.nth(params.nth)
        await locator.hover()
        resolved_nth = count - 1 if params.nth == -1 else params.nth
        return ActionResult(extracted_content=f"Hovered over '{params.selector}' (nth={resolved_nth} of {count} matches) on {page.url}")
    except Exception as e:
        return ActionResult(error=f"hover_by_selector failed: {e}")


@controller.registry.action(
    "Hover over exact pixel coordinates on the page using Playwright. "
    "Use when you know the screen position of the target element.",
    param_model=HoverByCoordinatesAction,
)
async def hover_by_coordinates(params: HoverByCoordinatesAction) -> ActionResult:
    page = await _get_active_page()
    if page is None:
        return ActionResult(error="Playwright: no active page found. Cannot hover.")
    try:
        await page.mouse.move(params.x, params.y)
        return ActionResult(extracted_content=f"Hovered at coordinates ({params.x}, {params.y}) on {page.url}")
    except Exception as e:
        return ActionResult(error=f"hover_by_coordinates failed: {e}")


@controller.registry.action(
    "Hover over a browser-use indexed element by its [N] index (the number shown in the DOM tree). "
    "Resolves the element's bounding box from browser-use's internal state and moves the mouse to its center. "
    "Use this to reveal hover-triggered UI such as a section's right-edge action buttons. "
    "More robust than CSS selectors because it does not depend on class names.",
    param_model=HoverByIndexAction,
)
async def hover_by_index(params: HoverByIndexAction, browser_session: BrowserSession) -> ActionResult:
    page = await _get_active_page()
    if page is None:
        return ActionResult(error="Playwright: no active page found. Cannot hover.")
    try:
        selector_map = await browser_session.get_selector_map()
        if params.index not in selector_map:
            return ActionResult(error=f"hover_by_index: no element with index [{params.index}] in selector_map")
        node = selector_map[params.index]
        if node.absolute_position is None:
            return ActionResult(error=f"hover_by_index: element [{params.index}] has no bounding box (not visible?)")
        bbox = node.absolute_position
        x = bbox.x + bbox.width / 2
        y = bbox.y + bbox.height / 2
        await page.mouse.move(x, y)
        return ActionResult(
            extracted_content=f"Hovered at center of [{params.index}]: ({x:.0f}, {y:.0f}), bbox={bbox.width:.0f}x{bbox.height:.0f}"
        )
    except Exception as e:
        return ActionResult(error=f"hover_by_index failed: {e}")


@controller.registry.action(
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

        # Step 1: hover the chart to trigger the section's hover state (buttons fade in)
        await page.mouse.move(hover_x, hover_y)
        await page.wait_for_timeout(params.wait_ms)

        # Step 2: find candidate buttons via locator (DOM query only, no mouse motion)
        buttons = page.get_by_label(params.button_aria_label, exact=True)
        count = await buttons.count()
        if count == 0:
            return ActionResult(error=f"No buttons with aria-label='{params.button_aria_label}' in DOM after hover")

        # Step 3: pick the button whose Y-center falls in the hovered chart's row, collect all bboxes for diagnostics
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

        # Step 4: raw mouse click at the button's center — no actionability wait, hover state preserved
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


async def main():
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "ai02-397001")

    if not project:
        print("[ERROR] Set GOOGLE_CLOUD_PROJECT env var")
        return

    print(f"\n{'='*70}")
    print(f"Manual Task Test — Pro LLM | Project: {project}")
    print(f"{'='*70}\n")

    launch_chrome()
    await asyncio.sleep(15)
    await connect_playwright_to_cdp()

    llm = ChatGoogle(
        model='gemini-3-flash-preview',
        project=project,
        location=location,
        vertexai=True,
        temperature=0.5,
        thinking_level='low'
    )

    browser = Browser(
        cdp_url="http://127.0.0.1:9222",
        disable_security=True,
        wait_between_actions=0.5,
        minimum_wait_page_load_time=0.5,
    )

    log_dir = os.path.join(os.path.dirname(__file__), "test_manual_logs")
    os.makedirs(log_dir, exist_ok=True)

    agent = Agent(
        task=TASK,
        llm=llm,
        browser=browser,
        controller=controller,
        # use_vision='auto',
        # override_system_message=SYSTEM_PROMPT_PRO,
        extend_system_message=SYSTEM_PROMPT,
        flash_mode=False,
        use_thinking=True
    )

    try:
        result = await agent.run()

        if result and result.is_done():
            print("\n[SUCCESS] All steps completed")
        else:
            errors = [e for e in result.errors() if e] if result else []
            print(f"\n[WARNING] Task may not have completed. Errors: {errors}")

        if result and result.history:
            print(f"Final URL: {result.history[-1].state.url}")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        if _playwright_browser:
            await _playwright_browser.close()
        if _playwright_instance:
            await _playwright_instance.stop()
        subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
        logger.info("Chrome cleaned up")


if __name__ == "__main__":
    asyncio.run(main())
