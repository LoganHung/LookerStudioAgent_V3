"""
Manual task test — Flash LLM, single agent, hardcoded task.

Usage:
    python test_manual_task.py
    python test_manual_task.py --url https://lookerstudio.google.com/...
"""
import asyncio
import argparse
import logging
import subprocess
import sys
import os
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
from browser_use import ChatGoogle


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
    import time; time.sleep(2)

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
Looker Studio Guide:
    - The canvas has sections stacked vertically. Each section holds charts side by side.
    - The first section is the report title — do NOT modify it.
    - Empty sections show an 'Add chart in placeholder' button in center.
    - Populated sections show an 'Add a chart' button on the section edge.
    - Property panel (right side): has 'Setup' and 'Style' tabs.
    - Data panel (far right): has a search bar — NEVER type metric/dimension names there. Only use the Setup tab in the property panel.
    - Toggle switches look like on/off sliders.
    - Section style menu: button with aria-label="Open style menu"
    - Alignment buttons: aria-label="Stretch", "Left", "Center", "Right"
    - Shadow button: aria-label="Add border shadow"

Mode: INSTRUCTIONAL — follow each numbered step exactly as written.
- Execute one action per step.
- Do not use toolbar buttons (except for adding a text box).
- When stuck or repeating, send key: "Escape"
- If an option is missing after 3 attempts, skip and continue.
"""


# =============================================================================
# TASK
# =============================================================================
TASK = """
The report is already open. If not, navigate to:
https://lookerstudio.google.com/reporting/99079d30-111d-4ee8-86ed-d86badd8ada3/page/HsstF/edit

Wait for the page to fully load before starting.

---

SECTION SETUP
Add a new empty section by clicking the '+' button below the last existing section.
Wait for the new section to appear before continuing.

---

CHART 1 — Dwell Trend Ratio

Add a Bar chart to the new section by clicking the 'add chart' or '+' button inside it.
Select 'Bar chart' from the chart picker.

In the Setup tab of the property panel:
- Click the existing dimension chip and replace it with: bin_dwell_trend_ratio
- Click 'Add dimension' and select: target_label_name
- Click the existing metric chip and replace it with: entity_id, aggregation set to COUNT

In the Style tab of the property panel:
- Enable 'Show title' and type: Dwell Trend Ratio — Is Connection Time Shrinking?
- Enable the X-axis title
- Enable the Y-axis title

---

CHART 2 — RSSI Fluctuation

Add another Bar chart to the same section.
Select 'Bar chart' from the chart picker.

In the Setup tab:
- Click the existing dimension chip and replace it with: bin_rssi_fluctuation_10m
- Click 'Add dimension' and select: target_label_name
- Click the existing metric chip and replace it with: entity_id, aggregation set to COUNT

In the Style tab:
- Enable 'Show title' and type: RSSI Fluctuation (10m) — How Unstable Is the Signal?
- Enable the X-axis title
- Enable the Y-axis title

---

CHART 3 — TX Rate Drop Ratio

Add another Bar chart to the same section.
Select 'Bar chart' from the chart picker.

In the Setup tab:
- Click the existing dimension chip and replace it with: bin_tx_rate_drop_ratio
- Click 'Add dimension' and select: target_label_name
- Click the existing metric chip and replace it with: entity_id, aggregation set to COUNT

In the Style tab:
- Enable 'Show title' and type: TX Rate Drop Ratio — Does Throughput Degrade After Switching?
- Enable the X-axis title
- Enable the Y-axis title

---

SECTION ARRANGEMENT
After all 3 charts are added, find the section layout or arrangement option for this section.
Set the arrangement to 'Stretch' so the charts fill the section width evenly.

---

FOOTER SECTION
Add one more new empty section below the current last section.
Inside it, add a Text element and set its content to:
Looker Studio Agent created the dashboard on 04/01/2026
"""


# =============================================================================
# MAIN
# =============================================================================
async def main():
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", 'ai02-397001')
    llm = ChatGoogle(
        model="gemini-3.1-pro-preview",
        project=project,
        location=location,
        vertexai=True,
        temperature=0.5,
        thinking_level="low",
    )

    print(f"\n{'='*70}")
    print(f"Manual Task Test — Flash LLM | Project: {project}")
    print(f"{'='*70}\n")

    launch_chrome()
    await asyncio.sleep(15)

    CDP_URL = "http://127.0.0.1:9222"

    controller = Controller()

    browser = Browser(
        cdp_url=CDP_URL,
        disable_security=True,
        wait_between_actions=1.0,
        minimum_wait_page_load_time=1.0,
    )

    agent = Agent(
        task=TASK,
        llm=llm,
        browser=browser,
        controller=controller,
        use_vision=False,
        extend_system_message=SYSTEM_PROMPT,
        use_thinking=True,
        enable_planning=True,
        flash_mode=False,
    )

    result = await agent.run()

    if result and not result.is_done():
        errors = [e for e in result.errors() if e]
        if errors:
            print(f"\n[WARNING] Agent had errors: {errors}")
        else:
            print(f"\n[WARNING] Agent may not have completed fully")
    else:
        print(f"\n[SUCCESS] Task completed")

    try:
        if result and result.history:
            final_url = result.history[-1].state.url
            print(f"Final URL: {final_url}")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
