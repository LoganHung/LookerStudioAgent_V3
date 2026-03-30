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


# =============================================================================
# CONTROLLER (no vision_click needed for responsive layout)
# =============================================================================
def create_controller() -> Controller:
    controller = Controller()
    # controller.registry.exclude_action('evaluate')
    logger.info("Controller created (responsive mode — no vision_click)")
    all_actions = list(controller.registry.registry.actions.keys())
    logger.info(f"   Registered actions: {all_actions}")
    return controller


# =============================================================================
# TASK COMPILER
# =============================================================================
from task_compiler import compile_config


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
# MAIN
# =============================================================================
async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Looker Studio Automation")
    parser.add_argument("--config", type=str, required=True, help="Path to dashboard_config.json")
    args = parser.parse_args()

    print(f"\nReading configuration from: {args.config}\n")

    compiled = compile_config(args.config)
    task = compiled["task_string"]
    vertex_ai_project_id = compiled["vertex_ai_project_id"]
    user_data_dir = compiled["user_data_dir"]
    skipped_configs = compiled.get("skipped_configs", [])

    print(f"Vertex AI Project ID: {vertex_ai_project_id}")
    print("=" * 60)
    print(task)
    print("=" * 60 + "\n")

    if not vertex_ai_project_id:
        print("[ERROR] vertex_ai_project_id is required in the config file")
        return

    project = vertex_ai_project_id
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

    controller = create_controller()
    # controller.set_coordinate_clicking(True)

    llm = ChatGoogle(
        model="gemini-3.1-pro-preview",
        project=project, location=location, vertexai=True,
        temperature=0.5, thinking_level="low",
    )

    if not user_data_dir:
        print("[ERROR] user_data_dir is missing from config. Run: bash config_helper.sh set_user_data_dir")
        return
    launch_chrome_linux(user_data_dir)
    await asyncio.sleep(10)

    browser = Browser(
        cdp_url="http://127.0.0.1:9222",
        disable_security=True,
        wait_between_actions=0.1,
        minimum_wait_page_load_time=0.1,
        # headless=True
    )
    # JavaScript Patterns (use these with evaluate()):

    # 1. ADD CHART TO THE LAST SECTION (when section already has charts):
    #    (function(){var sections=document.querySelectorAll('.section-container');var last=sections[sections.length-1];var btn=last.querySelector('.add-chart-button');if(btn){btn.click();return 'clicked add-chart on last section'}return 'button not found'})()

    # 2. ADD CHART TO EMPTY SECTION (placeholder button):
    #    (function(){var btn=document.querySelector('.placeholder-add-chart-button');if(btn){btn.click();return 'clicked placeholder add-chart'}return 'no placeholder found'})()

    # 3. ADD NEW SECTION (click the + button below the last section):
    #    (function(){var btns=document.querySelectorAll('.add-section-button');var last=btns[btns.length-1];if(last){last.click();return 'clicked add-section'}return 'not found'})()

    # 4. CLICK OPEN STYLE MENU on a specific section:
    #    (function(){var sections=document.querySelectorAll('.section-container');var target=sections[INDEX];var btn=target.querySelector('.open-style-menu-button');if(btn){btn.click();return 'opened style menu'}return 'not found'})()
    #    Replace INDEX with the section number (0-based).

    # 5. CLICK STRETCH alignment:
    #    (function(){var btn=document.querySelector('[aria-label="Stretch"]');if(btn){btn.click();return 'clicked stretch'}return 'not found'})()

    # 6. SWITCH TO SETUP or STYLE TAB:
    #    (function(){var tabs=document.querySelectorAll('.mdc-tab');for(var t of tabs){if(t.textContent.trim()==='Setup'){t.click();return 'switched to Setup'}}return 'tab not found'})()
    #    Replace 'Setup' with 'Style' as needed.
    # - Click at the coordinate (1910, 700) once you finish configure a chart's metric, style, and setup, then use screenshot to check it is configure successfully.
    SYSTEM_PROMPT = """
    Extra Rules:
    - Wait for 1 second between each action.
    - Must Write a todo.md initially, and complete all items in todo.md by following the task instruction.
    - Be extremely concise and direct in your responses
    - Get to the goal as quickly as possible    
    - Use multi-action sequences whenever possible to reduce steps
        - when you deal with anything related to drop-down menu/page, use one action per steps.

    Looker Studio DOM Guide:
        - Canvas: class="mainBlock responsive-layout"
        - Sections: class="section-container" with unique block-id attributes
        - Selected section has class "selected" with blue border
        - Empty sections have class="placeholder-add-chart-button" button in center
        - Populated sections have class="add-chart-button" on section edge
        - Property panel: class="property-panel", tabs 'Setup' and 'Style' (class mdc-tab)
        - Data panel (far right): has a search bar — NEVER type metric/dimension names there. Only use the Setup tab in the property panel.
        - Toggle switches: class="mat-mdc-slide-toggle"
        - Section style menu: aria-label="Open style menu", class="open-style-menu-button"
        - Alignment buttons: aria-label="Stretch", "Left", "Center", "Right"

    Recovery from loops:
    - When repeating actions or page not changing, you may send key: "Escape"
    - If a specific option is missing after 3 attempts, skip it and continue.
    """
        # - The TOP TOOLBAR also has 'Add a chart' — NEVER use it. Use evaluate() to target the section button.
    agent = Agent(
        task=task, llm=llm, browser=browser,
        controller=controller,
        use_vision=False,
        extend_system_message=SYSTEM_PROMPT,
        use_thinking=False,           
        enable_planning=False,        
        flash_mode=False, # flash mode is easy to lost control
        # max_actions_per_step=3
    )

    try:
        print("\n" + "=" * 80)
        print("STARTING AGENT EXECUTION")
        print("=" * 80 + "\n")
        await agent.run()
        print("\n" + "=" * 80)
        print("[SUCCESS] AGENT EXECUTION COMPLETED")
        print("=" * 80)

        # Report skipped configurations
        if skipped_configs:
            print("\n[Config Filter Report — the following were auto-skipped]")
            for msg in skipped_configs:
                print(f"  ⚠ {msg}")
            print()
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if browser:
            try:
                if hasattr(browser, 'stop'):
                    await browser.stop()
                elif hasattr(browser, 'close'):
                    await browser.close()
            except Exception as e:
                print(f"Cleanup warning: {e}")

if __name__ == "__main__":
    asyncio.run(main())
