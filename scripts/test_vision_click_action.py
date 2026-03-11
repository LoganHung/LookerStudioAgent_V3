"""
Looker Studio Automation - Vision Click with Browser-Use
"""
import asyncio
import logging
import sys
import os
import subprocess
import base64
import time
import json
import re
from logging.handlers import RotatingFileHandler
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
from browser_use.agent.views import ActionResult
from browser_use import ChatGoogle
from google.genai import types


# =============================================================================
# VISION COORDINATE FINDER
# =============================================================================
class VisionCoordinateFinder:
    """Finds coordinates using Gemini with code execution"""

    def __init__(self, project: str, location: str):
        self._call_count = 0

        self.vision_logger = logging.getLogger('VisionCoordinateFinder')
        self.vision_logger.setLevel(logging.DEBUG)
        self.vision_logger.propagate = False

        os.makedirs('vision_logs', exist_ok=True)
        fh = RotatingFileHandler(
            'vision_logs/vision_coordinate_finder.log',
            maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.vision_logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.vision_logger.addHandler(ch)

        self.vision_logger.info("=" * 80)
        self.vision_logger.info("VisionCoordinateFinder initialized")
        self.vision_logger.info(f"Log file: vision_logs/vision_coordinate_finder.log")
        self.vision_logger.info("=" * 80)

        self.vision_llm = ChatGoogle(
            model="gemini-3-flash-preview",
            project=project, location=location, vertexai=True,
            temperature=0.0, thinking_level="minimal",
            config={
                'system_instruction':
                """
                # ROLE
                You are a Coordinate Calculation Specialist, you think and find right coordinate using ROI(Region of Interesting) strategy but not guessing. Your mission is
                1. To extract precise (x, y) pixel coordinates from images via Python-based analysis.
                2. To optimize the token usage without break the result.

                # OPERATIONAL CONSTRAINTS
                - STARTING OFFSET: Ignore all elements where y < 150 (reserved for system toolbars).
                - SEARCH FOCUS: Define a Region of Interest (ROI) based on the user description before executing search logic to minimize processing.
                - LIBRARIES:
                    - ALLOWED: PIL (Pillow), numpy, base64, io, json.
                    - FORBIDDEN: cv2 (OpenCV), matplotlib, tensorflow.
                - EXECUTION LIMIT: Maximum 3 attempts. Aim for success in 1. No redundant pixel / color verification blocks after finding the coordinate.
                - VERFICATION LIMIT: You can onlt verify the coordinate ONCE. It is strictly forbidden to run pixel-by-pixel checking.

                # BOUNDARY DETECTION HIERARCHY
                When determining edges, use this priority logic:
                1. DEFINED BORDERS: Use the exact pixel edge of any solid-colored stroke (e.g., selection frames).
                2. SHADOW ORIGIN: Use the sharp line where the component color meets a shadow. Ignore the blur/gradient.
                3. SEMANTIC PROJECTION: For invisible/white-on-white edges, set the boundary 15 pixels beyond the outermost text/label element.

                # EXECUTION WORKFLOW
                1. ANALYZE: Identify the target's visual characteristics and find the anchor (boundary box, shadow, or corner),
                   then find the ROI(Region of Interest).
                2. EXECUTE : Write One Python Code to fin the coordinate (x,y) of the anchor
                3. VALIDATE:
                    1.If the element is a large UI component (canvas/panel), ensure the detected region is at least 100x100 pixels.
                    2.Verify the coordiante (x,y) is matched to the description.
                4. OUTPUT: Provide the result strictly in the format below.

                # OUTPUT FORMAT
                Final answer must be a single JSON object:
                {"x": <int>, "y": <int>}

                """,
                'tools': [types.Tool(code_execution=types.ToolCodeExecution)]
            },
        )

        # Monkey patch to capture raw responses with code execution details
        self._raw_response = None
        client = self.vision_llm.get_client()
        original_generate = client.aio.models.generate_content

        async def wrapped_generate_content(**kwargs):
            response = await original_generate(**kwargs)
            self._raw_response = response
            return response

        client.aio.models.generate_content = wrapped_generate_content

    async def find_coordinates(self, screenshot_base64: str, description: str) -> dict:
        from browser_use.llm.messages import UserMessage, ContentPartTextParam, ContentPartImageParam

        self._call_count += 1
        start_time = time.time()

        self.vision_logger.info("=" * 80)
        self.vision_logger.info(f"VISION COORDINATE FINDER - Call #{self._call_count}")
        self.vision_logger.info(f"   Target: {description}")
        self.vision_logger.info("=" * 80)

        prompt = f"""Find the pixel coordinates (x, y) of: {description}

        Use Python code with PIL/numpy to analyze the screenshot.
        Return ONLY the JSON result: {{"x": <int>, "y": <int>}}"""

        message = UserMessage(content=[
            ContentPartTextParam(type='text', text=prompt),
            ContentPartImageParam(type='image_url', image_url={'url': screenshot_base64})
        ])

        logger.info(f"Finding coordinates for: {description}")
        response = await self.vision_llm.ainvoke([message])

        execution_time = time.time() - start_time
        tokens_used = response.usage.total_tokens if response.usage else 0

        # Log code execution details
        code_execution_count = 0
        if self._raw_response and hasattr(self._raw_response, 'candidates') and self._raw_response.candidates:
            parts = self._raw_response.candidates[0].content.parts
            code_execution_count = sum(1 for p in parts if hasattr(p, 'executable_code'))
            self.vision_logger.info(f"Response: {len(parts)} parts, {code_execution_count} code executions")

            for part in parts:
                try:
                    if part.executable_code:
                        self.vision_logger.debug(f"Code: {part.executable_code}")
                except (AttributeError, Exception):
                    pass
                try:
                    if part.code_execution_result:
                        self.vision_logger.debug(f"Result: {part.code_execution_result.output}")
                except (AttributeError, Exception):
                    pass

        coordinates = self._extract_coordinates(response.completion)

        self.vision_logger.info(f"Coordinates: x={coordinates['x']}, y={coordinates['y']}")
        self.vision_logger.info(f"Tokens: {tokens_used:,}, Time: {execution_time:.2f}s, Iterations: {code_execution_count}")
        logger.info(f"Found coordinates: x={coordinates['x']}, y={coordinates['y']} ({execution_time:.2f}s)")

        return {
            "x": coordinates["x"], "y": coordinates["y"],
            "tokens_used": tokens_used, "execution_time": execution_time,
            "code_execution_count": code_execution_count
        }

    def _extract_coordinates(self, text: str) -> dict:
        # Try JSON pattern
        matches = re.findall(r'\{[^}]*"x"[^}]*"y"[^}]*\}', text, re.IGNORECASE)
        if matches:
            try:
                coords = json.loads(matches[0])
                if "x" in coords and "y" in coords:
                    return {"x": int(coords["x"]), "y": int(coords["y"])}
            except Exception:
                pass

        # Try x=123, y=456 pattern
        x_match = re.search(r'["\']?x["\']?\s*[:=]\s*(\d+)', text, re.IGNORECASE)
        y_match = re.search(r'["\']?y["\']?\s*[:=]\s*(\d+)', text, re.IGNORECASE)
        if x_match and y_match:
            return {"x": int(x_match.group(1)), "y": int(y_match.group(1))}

        raise ValueError(f"Could not extract coordinates from: {text[:200]}...")


# =============================================================================
# VISION CLICK CONTROLLER
# =============================================================================
def create_vision_click_controller(project: str, location: str) -> Controller:
    controller = Controller()
    controller.set_coordinate_clicking(True)
    controller.registry.exclude_action('evaluate')
    vision_finder = VisionCoordinateFinder(project=project, location=location)

    @controller.action(
        description="Click at location found by calculating the coordinates from screenshot. Use for canvas/drawing areas where element index is unavailable."
    )
    async def vision_click(description: str, browser_session: Browser) -> ActionResult:
        try:
            logger.info(f"\n{'='*80}")
            logger.info(f"VISION_CLICK ACTION CALLED!")
            logger.info(f"{'='*80}")
            logger.info(f"   Description: {description}")

            page = await browser_session.get_current_page()
            screenshot_base64_str = await page.screenshot()
            screenshot_base64 = f"data:image/png;base64,{screenshot_base64_str}"

            result = await vision_finder.find_coordinates(
                screenshot_base64=screenshot_base64, description=description
            )
            x, y = result['x'], result['y']

            from browser_use.browser.events import ClickCoordinateEvent
            event = browser_session.event_bus.dispatch(
                ClickCoordinateEvent(coordinate_x=x, coordinate_y=y, force=True)
            )
            await event
            await event.event_result(raise_if_any=True, raise_if_none=False)

            memory = f"Used vision to find '{description}' at coordinates ({x}, {y}) and clicked there"
            logger.info(f"vision_click success: {memory}")
            return ActionResult(
                extracted_content=memory,
                metadata={'coordinates': {'x': x, 'y': y}, 'tokens_used': result['tokens_used'], 'execution_time': result['execution_time']}
            )
        except Exception as e:
            error_msg = f"Vision click failed: {str(e)}"
            logger.error(error_msg)
            return ActionResult(error=error_msg)

    logger.info("Vision-click controller created")
    all_actions = list(controller.registry.registry.actions.keys())
    logger.info(f"   Registered actions: {all_actions}")
    return controller


# =============================================================================
# TASK COMPILER (replaces old build_dynamic_task)
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
        "--start-maximized",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
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

    print(f"Vertex AI Project ID: {vertex_ai_project_id}")
    print("=" * 60)
    print(task)
    print("=" * 60 + "\n")

    if not vertex_ai_project_id:
        print("[ERROR] vertex_ai_project_id is required in the config file")
        return

    project = vertex_ai_project_id
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

    controller = create_vision_click_controller(project=project, location=location)

    llm = ChatGoogle(
        model="gemini-3-flash-preview",
        project=project, location=location, vertexai=True,
        temperature=1.0, thinking_level="minimal",
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
    )

    SYSTEM_PROMPT = """
    Task Rules:
    - Forbidden to use vision_click if not mention in the task.
    - Do Not Trigger vision_click to find element, button, icon, and etc,.
    - Do NOT use multi-action for dropdown menus or field pickers. Wait for each to render.
    - Do not scroll the canvas when configuring Style tab.
    Speed optimization instructions:    
    - Be extremely concise and direct in your responses
    - Get to the goal as quickly as possible
    - Use multi-action sequences whenever possible to reduce steps
    """

    agent = Agent(
        task=task, llm=llm, browser=browser,
        controller=controller, use_vision=True,
        extend_system_message=SYSTEM_PROMPT,
        fast_mode=True,
    )

    try:
        print("\n" + "=" * 80)
        print("STARTING AGENT EXECUTION")
        print("=" * 80 + "\n")
        await agent.run()
        print("\n" + "=" * 80)
        print("[SUCCESS] AGENT EXECUTION COMPLETED")
        print("=" * 80)
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
