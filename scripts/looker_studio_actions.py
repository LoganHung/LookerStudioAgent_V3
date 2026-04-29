"""
Custom browser-use controller actions for Looker Studio automation.

These replace unreliable LLM-driven interactions with deterministic JavaScript.
Each action targets a specific failure pattern observed in production runs.
"""
import logging
from pydantic import BaseModel, Field

from browser_use import Controller
from browser_use.agent.views import ActionResult
from browser_use.browser import BrowserSession

logger = logging.getLogger(__name__)


# =============================================================================
# JavaScript snippets — kept as constants for readability
# =============================================================================

JS_SEARCH_FIELD_PICKER = """
(function(fieldName) {
    // Find the visible field picker search input (inside the overlay, not the Data panel)
    var overlays = document.querySelectorAll('[id^="cdk-overlay-"]');
    var input = null;
    for (var i = overlays.length - 1; i >= 0; i--) {
        var candidate = overlays[i].querySelector('input[type="search"]');
        if (candidate && candidate.offsetParent !== null) {
            input = candidate;
            break;
        }
    }
    if (!input) return JSON.stringify({ok: false, error: 'no picker search input found'});

    // Clear and type using native input setter to trigger Angular change detection
    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputValueSetter.call(input, '');
    input.dispatchEvent(new Event('input', {bubbles: true}));

    // Small delay for clearing, then type the search term
    return new Promise(function(resolve) {
        setTimeout(function() {
            input.focus();
            nativeInputValueSetter.call(input, fieldName);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));

            // Wait for virtual scroll to filter results
            setTimeout(function() {
                var viewport = input.closest('[id^="cdk-overlay-"]')
                    .querySelector('cdk-virtual-scroll-viewport');
                if (!viewport) {
                    resolve(JSON.stringify({ok: false, error: 'no virtual scroll viewport'}));
                    return;
                }
                var items = viewport.querySelectorAll('[class*="chippy-bag-item"]');
                if (items.length === 0) {
                    resolve(JSON.stringify({ok: false, error: 'no results for: ' + fieldName}));
                    return;
                }

                // Find exact or best match
                var matched = null;
                for (var j = 0; j < items.length; j++) {
                    var text = items[j].textContent.trim().toLowerCase();
                    if (text === fieldName.toLowerCase()) {
                        matched = items[j];
                        break;
                    }
                }
                if (!matched) matched = items[0];  // first result as fallback

                matched.click();
                resolve(JSON.stringify({
                    ok: true,
                    selected: matched.textContent.trim(),
                    total_results: items.length
                }));
            }, 500);
        }, 200);
    });
})('%FIELD_NAME%')
"""

JS_ADD_SECTION = """
(function() {
    // Always use the LAST add-section button — querySelector returns the first,
    // which inserts above section 1. querySelectorAll + last gives the bottom button.
    var btns = document.querySelectorAll('.add-section-button');
    if (btns.length > 0) {
        var addBtn = btns[btns.length - 1];
        addBtn.scrollIntoView({block: 'center'});
        addBtn.click();
        return JSON.stringify({ok: true, method: 'add-section-button-last', count: btns.length});
    }

    // Fallback: scroll to last section and trigger hover to reveal button
    var sections = document.querySelectorAll('.section-container');
    if (sections.length === 0) return JSON.stringify({ok: false, error: 'no sections found'});
    var lastSection = sections[sections.length - 1];
    lastSection.scrollIntoView({block: 'end'});

    lastSection.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
    lastSection.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));

    return new Promise(function(resolve) {
        setTimeout(function() {
            var allBtns = document.querySelectorAll('.add-section-button');
            if (allBtns.length > 0) {
                var btn = allBtns[allBtns.length - 1];
                btn.click();
                resolve(JSON.stringify({ok: true, method: 'hover-revealed-last'}));
                return;
            }
            // Last resort: proximity search below the last section
            var lastRect = lastSection.getBoundingClientRect();
            var candidates = document.querySelectorAll('button');
            for (var i = 0; i < candidates.length; i++) {
                var rect = candidates[i].getBoundingClientRect();
                if (rect.top > lastRect.bottom - 20 && rect.top < lastRect.bottom + 150) {
                    candidates[i].click();
                    resolve(JSON.stringify({ok: true, method: 'proximity-below-last'}));
                    return;
                }
            }
            resolve(JSON.stringify({ok: false, error: 'add-section button not found after hover'}));
        }, 500);
    });
})()
"""

JS_ENABLE_CHART_TITLE = """
(function(titleText) {
    // Scroll to top of Style panel to find Show title
    var stylePanel = document.querySelector('.property-panel-container')
                  || document.querySelector('[class*="style-panel"]')
                  || document.querySelector('[class*="property-panel"]');

    var toggle = document.querySelector('button[aria-label="Show title"]');
    if (!toggle) return JSON.stringify({ok: false, error: 'Show title toggle not found'});

    toggle.scrollIntoView({block: 'center'});

    // Enable if not already on
    if (!toggle.classList.contains('mdc-switch--checked')) {
        toggle.click();
    }

    return new Promise(function(resolve) {
        setTimeout(function() {
            // Find the title input field
            var titleInput = document.querySelector('input[aria-label="textinput"]');
            if (!titleInput) {
                resolve(JSON.stringify({ok: true, toggled: true, input: false,
                    error: 'title input not found after toggle'}));
                return;
            }

            titleInput.scrollIntoView({block: 'center'});
            titleInput.focus();
            titleInput.select();

            // Use native setter for Angular compatibility
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(titleInput, titleText);
            titleInput.dispatchEvent(new Event('input', {bubbles: true}));
            titleInput.dispatchEvent(new Event('change', {bubbles: true}));
            titleInput.dispatchEvent(new Event('blur', {bubbles: true}));

            resolve(JSON.stringify({ok: true, toggled: true, input: true, title: titleText}));
        }, 300);
    });
})('%TITLE_TEXT%')
"""

JS_SET_AGGREGATION = """
(function(targetAgg) {
    // Find the metric chip's aggregation button (not the text label)
    var aggButton = document.querySelector('#aggregationButton');
    if (!aggButton) {
        // Fallback: find the chip and click its icon area
        var chips = document.querySelectorAll('ng2-concept-chip');
        var metricChip = null;
        for (var i = chips.length - 1; i >= 0; i--) {
            var parent = chips[i].closest('[class*="metric"]');
            if (parent) { metricChip = chips[i]; break; }
        }
        if (!metricChip) return JSON.stringify({ok: false, error: 'no metric chip found'});

        var icon = metricChip.querySelector('.aggregation-type-icon, mat-icon');
        if (icon) {
            icon.click();
            return new Promise(function(resolve) {
                setTimeout(function() {
                    var aggBtn2 = document.querySelector('#aggregationButton');
                    if (aggBtn2) {
                        aggBtn2.click();
                        setTimeout(function() {
                            var options = document.querySelectorAll('mat-option, [role="option"]');
                            for (var j = 0; j < options.length; j++) {
                                if (options[j].textContent.trim().toLowerCase() === targetAgg.toLowerCase()) {
                                    options[j].click();
                                    resolve(JSON.stringify({ok: true, selected: targetAgg}));
                                    return;
                                }
                            }
                            resolve(JSON.stringify({ok: false, error: 'aggregation option not found: ' + targetAgg}));
                        }, 300);
                    } else {
                        resolve(JSON.stringify({ok: false, error: 'aggregation button not found after icon click'}));
                    }
                }, 300);
            });
        }
        return JSON.stringify({ok: false, error: 'no aggregation icon on chip'});
    }

    // Direct path: aggregation button is already visible (edit panel is open)
    aggButton.click();
    return new Promise(function(resolve) {
        setTimeout(function() {
            var options = document.querySelectorAll('mat-option, [role="option"]');
            for (var j = 0; j < options.length; j++) {
                if (options[j].textContent.trim().toLowerCase() === targetAgg.toLowerCase()) {
                    options[j].click();
                    resolve(JSON.stringify({ok: true, selected: targetAgg}));
                    return;
                }
            }
            resolve(JSON.stringify({ok: false, error: 'aggregation option not found: ' + targetAgg}));
        }, 300);
    });
})('%AGGREGATION%')
"""

JS_ENABLE_AXIS_TITLES = """
(function(axisIndex) {
    // Enable Show axes first (prerequisite)
    var showAxes = document.querySelector('button[aria-label="Show axes"]');
    if (showAxes && !showAxes.classList.contains('mdc-switch--checked')) {
        showAxes.scrollIntoView({block: 'center'});
        showAxes.click();
    }

    return new Promise(function(resolve) {
        setTimeout(function() {
            var toggles = document.querySelectorAll('button[aria-label="Show axis title"]');
            if (!toggles[axisIndex]) {
                resolve(JSON.stringify({ok: false, error: 'Show axis title[' + axisIndex + '] not found, count=' + toggles.length}));
                return;
            }
            var t = toggles[axisIndex];
            t.scrollIntoView({block: 'center'});
            if (!t.classList.contains('mdc-switch--checked')) {
                t.click();
                resolve(JSON.stringify({ok: true, action: 'enabled', index: axisIndex}));
            } else {
                resolve(JSON.stringify({ok: true, action: 'already_on', index: axisIndex}));
            }
        }, 300);
    });
})(%AXIS_INDEX%)
"""

JS_ADD_CHART_TO_SECTION = """
(function(sectionIdx) {
    var s = document.querySelectorAll('.section-container')[sectionIdx];
    if (!s) return JSON.stringify({ok: false, error: 'section ' + sectionIdx + ' not found'});
    var btn = s.querySelector('.placeholder-add-chart-button')
           || s.querySelector('.add-chart-button');
    if (btn) {
        btn.scrollIntoView({block: 'center'});
        btn.click();
        return JSON.stringify({ok: true, section: sectionIdx});
    }
    return JSON.stringify({ok: false, error: 'no add-chart button in section ' + sectionIdx});
})(%SECTION_IDX%)
"""

JS_SET_SECTION_STRETCH = """
(function(sectionIdx) {
    var s = document.querySelectorAll('.section-container')[sectionIdx];
    if (!s) return JSON.stringify({ok: false, error: 'section ' + sectionIdx + ' not found'});
    var btn = s.querySelector('.open-style-menu-button');
    if (!btn) return JSON.stringify({ok: false, error: 'style menu button not found'});

    btn.scrollIntoView({block: 'center'});
    btn.click();

    return new Promise(function(resolve) {
        setTimeout(function() {
            var stretch = document.querySelector('button[aria-label="Stretch"]');
            if (stretch) {
                stretch.click();
                resolve(JSON.stringify({ok: true, section: sectionIdx, style: 'stretch'}));
            } else {
                resolve(JSON.stringify({ok: false, error: 'Stretch button not found in menu'}));
            }
        }, 300);
    });
})(%SECTION_IDX%)
"""

JS_REPLACE_DIMENSION = """
(function(dimIndex) {
    // Click the dimension chip at the given index (0 = first/primary, 1 = second, etc.)
    // This REPLACES the chip rather than adding a new one via "Add dimension".
    // Dimension chips live inside the Setup tab's dimension section.
    var chips = document.querySelectorAll('ng2-concept-chip');
    // Looker Studio Setup tab: dimension chips come before metric chips.
    // Filter to chips that are NOT inside a metric container.
    var dimChips = [];
    for (var i = 0; i < chips.length; i++) {
        var chip = chips[i];
        // Walk up: if the chip is inside a container with 'metric' in its class, skip it
        var inMetric = false;
        var el = chip;
        for (var d = 0; d < 5; d++) {
            el = el.parentElement;
            if (!el) break;
            if (el.className && typeof el.className === 'string' && el.className.indexOf('metric') !== -1) {
                inMetric = true; break;
            }
        }
        if (!inMetric) dimChips.push(chip);
    }
    if (dimChips.length === 0) return JSON.stringify({ok: false, error: 'no dimension chips found'});
    if (dimIndex >= dimChips.length) return JSON.stringify({ok: false, error: 'dimIndex ' + dimIndex + ' out of range, found ' + dimChips.length});

    var target = dimChips[dimIndex];
    // Click the text label part of the chip (not the aggregation icon)
    var label = target.querySelector('[class*="chip-label"], [class*="chippy-label"], span')
             || target;
    label.scrollIntoView({block: 'center'});
    label.click();
    return JSON.stringify({ok: true, clicked: target.textContent.trim(), dimIndex: dimIndex, total: dimChips.length});
})(%DIM_INDEX%)
"""

JS_SET_REPORT_TITLE = """
(function(titleText) {
    // Target the canvas report title — the EDITOR node, not the viewer.
    // The viewer (ng2-textbox-viewer) is read-only; the editor (ng2-textbox-editor)
    // is a contenteditable div that appears when the title is selected/active.
    //
    // Strategy: double-click the viewer to activate the editor, then set text.
    var viewer = document.querySelector('ng2-textbox-viewer');
    if (!viewer) return JSON.stringify({ok: false, error: 'ng2-textbox-viewer not found'});

    // Double-click to enter edit mode
    viewer.scrollIntoView({block: 'center'});
    viewer.dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));

    return new Promise(function(resolve) {
        setTimeout(function() {
            var editor = document.querySelector('ng2-textbox-editor [contenteditable="true"]')
                      || document.querySelector('[contenteditable="true"][class*="title"]')
                      || document.querySelector('ng2-textbox-editor');
            if (!editor) {
                resolve(JSON.stringify({ok: false, error: 'contenteditable title editor not found after dblclick'}));
                return;
            }
            // Select all and replace
            editor.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, titleText);
            // Commit with blur
            editor.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
            resolve(JSON.stringify({ok: true, title: titleText}));
        }, 400);
    });
})('%TITLE_TEXT%')
"""

JS_SCROLL_TO_STYLE_OPTION = """
(function(ariaLabel) {
    // Scope search to property panel if available, else whole document
    var panel = document.querySelector('.property-panel-container')
             || document.querySelector('[class*="property-panel"]')
             || document.body;

    // 1. Exact aria-label match
    var target = panel.querySelector('[aria-label="' + ariaLabel + '"]');

    // 2. Partial aria-label match
    if (!target) {
        var candidates = panel.querySelectorAll('[aria-label]');
        for (var i = 0; i < candidates.length; i++) {
            if (candidates[i].getAttribute('aria-label').toLowerCase().indexOf(ariaLabel.toLowerCase()) !== -1) {
                target = candidates[i]; break;
            }
        }
    }

    // 3. Visible text content match (labels, headings, spans)
    if (!target) {
        var all = panel.querySelectorAll('label, span, div, button');
        for (var j = 0; j < all.length; j++) {
            if (all[j].childElementCount === 0 &&
                all[j].textContent.trim().toLowerCase() === ariaLabel.toLowerCase()) {
                target = all[j]; break;
            }
        }
    }

    if (!target) return JSON.stringify({ok: false, error: 'not found: ' + ariaLabel});
    target.scrollIntoView({block: 'center'});
    return JSON.stringify({ok: true, found: ariaLabel});
})('%ARIA_LABEL%')
"""

JS_ENABLE_SHADOW = """
(function() {
    var t = document.querySelector('button[aria-label="Add border shadow"]');
    if (!t) return JSON.stringify({ok: false, error: 'shadow toggle not found'});
    t.scrollIntoView({block: 'center'});
    if (!t.classList.contains('mdc-switch--checked')) {
        t.click();
        return JSON.stringify({ok: true, action: 'enabled'});
    }
    return JSON.stringify({ok: true, action: 'already_on'});
})()
"""

JS_ENABLE_DATA_LABELS = """
(function() {
    var t = document.querySelector('button[aria-label="Show data labels"]');
    if (!t) return JSON.stringify({ok: false, error: 'data labels toggle not found'});
    t.scrollIntoView({block: 'center'});
    if (!t.classList.contains('mdc-switch--checked')) {
        t.click();
        return JSON.stringify({ok: true, action: 'enabled'});
    }
    return JSON.stringify({ok: true, action: 'already_on'});
})()
"""


# =============================================================================
# Helper to run JS via CDP
# =============================================================================
async def _run_js(browser_session: BrowserSession, code: str) -> dict:
    """Execute JavaScript via CDP and return parsed JSON result."""
    import json
    cdp_session = await browser_session.get_or_create_cdp_session()
    result = await cdp_session.cdp_client.send.Runtime.evaluate(
        params={'expression': code, 'returnByValue': True, 'awaitPromise': True},
        session_id=cdp_session.session_id,
    )
    if result.get('exceptionDetails'):
        return {"ok": False, "error": result['exceptionDetails'].get('text', 'JS error')}
    value = result.get('result', {}).get('value', '')
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"ok": True, "raw": value}
    return {"ok": True, "raw": str(value)}


# =============================================================================
# Register all custom actions on a Controller
# =============================================================================
def register_looker_actions(controller: Controller) -> Controller:
    """Register all Looker Studio custom actions on the given controller."""

    @controller.registry.action(
        "Search and select a field in the currently open Looker Studio field picker. "
        "Use this INSTEAD of typing into the picker search input manually. "
        "The picker must already be open (from clicking a chip or 'Add dimension'/'Add metric').",
    )
    async def search_field_picker(
        field_name: str = Field(description="The exact field name to search for and select"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_SEARCH_FIELD_PICKER.replace('%FIELD_NAME%', field_name.replace("'", "\\'"))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(
                extracted_content=f"Selected field '{result.get('selected', field_name)}' from picker ({result.get('total_results', '?')} results)",
            )
        return ActionResult(error=f"search_field_picker failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Add a new empty section (row) below the last section in the Looker Studio report. "
        "Use this instead of trying to find and click the '+' button manually.",
    )
    async def add_section(
        _placeholder: str = Field(default="", description="unused"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        result = await _run_js(browser_session, JS_ADD_SECTION)
        if result.get("ok"):
            return ActionResult(
                extracted_content=f"New section added (method: {result.get('method', 'unknown')}). Wait for it to render.",
            )
        return ActionResult(error=f"add_section failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Click the add-chart button inside a specific section of the Looker Studio report. "
        "Handles both empty sections (placeholder button) and populated sections. "
        "After this, select the chart type from the picker that appears.",
    )
    async def add_chart_in_section(
        section_index: int = Field(description="Section index (0=title row, 1=first data row, 2=second data row, etc.)"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_ADD_CHART_TO_SECTION.replace('%SECTION_IDX%', str(section_index))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(
                extracted_content=f"Chart picker opened in section {section_index}. Now select the chart type.",
            )
        return ActionResult(error=f"add_chart_in_section failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Enable chart title and set its text in the Style tab. "
        "Scrolls to the 'Show title' toggle, enables it, and types the title text. "
        "The chart must be selected before calling this.",
    )
    async def set_chart_title(
        title_text: str = Field(description="The chart title text to set"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_ENABLE_CHART_TITLE.replace('%TITLE_TEXT%', title_text.replace("'", "\\'"))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            parts = []
            if result.get("toggled"):
                parts.append("title enabled")
            if result.get("input"):
                parts.append(f"text set to '{result.get('title', title_text)}'")
            return ActionResult(extracted_content=f"Chart title: {', '.join(parts)}")
        return ActionResult(error=f"set_chart_title failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Enable an axis title in the Style tab. Automatically enables 'Show axes' first if needed, "
        "then scrolls to the correct 'Show axis title' toggle and enables it. "
        "The chart must be selected and the Style tab active.",
    )
    async def enable_axis_title(
        axis: str = Field(description="Which axis: 'x' for dimension axis (index 0), 'y' for metric axis (index 1)"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        idx = 0 if axis.lower() in ('x', 'dimension', '0') else 1
        code = JS_ENABLE_AXIS_TITLES.replace('%AXIS_INDEX%', str(idx))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            axis_name = "X (dimension)" if idx == 0 else "Y (metric)"
            return ActionResult(
                extracted_content=f"Axis title {axis_name}: {result.get('action', 'done')}",
            )
        return ActionResult(error=f"enable_axis_title failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Set the aggregation type for the currently open metric edit panel. "
        "If the edit panel is not open, attempts to open it via the aggregation icon. "
        "Use this instead of manually clicking the aggregation dropdown.",
    )
    async def set_aggregation(
        aggregation_type: str = Field(description="Aggregation type: Count, Count Distinct, Sum, Avg, Min, Max, etc."),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_SET_AGGREGATION.replace('%AGGREGATION%', aggregation_type.replace("'", "\\'"))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(
                extracted_content=f"Aggregation set to '{result.get('selected', aggregation_type)}'",
            )
        return ActionResult(error=f"set_aggregation failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Set a section's layout to 'Stretch' so charts fill the width evenly. "
        "Opens the section style menu and clicks Stretch automatically.",
    )
    async def set_section_stretch(
        section_index: int = Field(description="Section index (0=title row, 1=first data row, etc.)"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_SET_SECTION_STRETCH.replace('%SECTION_IDX%', str(section_index))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(
                extracted_content=f"Section {section_index} set to Stretch layout",
            )
        return ActionResult(error=f"set_section_stretch failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Click a dimension chip at a specific index in the Setup tab to open the field picker for REPLACING it. "
        "Use index=0 for the first/primary dimension chip, index=1 for the second. "
        "Use this INSTEAD of 'click the existing dimension chip' — it reliably targets the right chip. "
        "After calling this, use search_field_picker to select the new field.",
    )
    async def replace_dimension(
        dim_index: int = Field(description="0 for first dimension chip, 1 for second, etc."),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_REPLACE_DIMENSION.replace('%DIM_INDEX%', str(dim_index))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(
                extracted_content=f"Opened field picker for dimension[{dim_index}] (was: '{result.get('clicked', '?')}', total chips: {result.get('total', '?')}). Now use search_field_picker.",
            )
        return ActionResult(error=f"replace_dimension failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Set the canvas report title on the Looker Studio page (the large 'Add report title' text). "
        "Double-clicks the title viewer to activate the editor, selects all, and types the new title. "
        "Use this instead of manually clicking and typing into the title area.",
    )
    async def set_report_title(
        title_text: str = Field(description="The report title text to set on the canvas"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_SET_REPORT_TITLE.replace('%TITLE_TEXT%', title_text.replace("'", "\\'"))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(extracted_content=f"Canvas report title set to '{result.get('title', title_text)}'")
        return ActionResult(error=f"set_report_title failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Scroll the Style panel to bring a specific option into view before interacting with it. "
        "Use this BEFORE any manual Style tab interaction (color swatches, font controls, dropdowns). "
        "Searches by aria-label, then partial aria-label, then visible text content.",
    )
    async def scroll_to_style_option(
        aria_label: str = Field(description="The aria-label or visible text of the Style panel element to scroll to"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        code = JS_SCROLL_TO_STYLE_OPTION.replace('%ARIA_LABEL%', aria_label.replace("'", "\\'"))
        result = await _run_js(browser_session, code)
        if result.get("ok"):
            return ActionResult(extracted_content=f"Scrolled Style panel to '{result.get('found', aria_label)}'")
        return ActionResult(error=f"scroll_to_style_option failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Enable 'Add border shadow' toggle in the Style tab. "
        "Scrolls to the toggle and enables it idempotently.",
    )
    async def enable_shadow(
        _placeholder: str = Field(default="", description="unused"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        result = await _run_js(browser_session, JS_ENABLE_SHADOW)
        if result.get("ok"):
            return ActionResult(extracted_content=f"Shadow: {result.get('action', 'done')}")
        return ActionResult(error=f"enable_shadow failed: {result.get('error', 'unknown')}")

    @controller.registry.action(
        "Enable 'Show data labels' toggle in the Style tab. "
        "Scrolls to the toggle and enables it idempotently.",
    )
    async def enable_data_labels(
        _placeholder: str = Field(default="", description="unused"),
        browser_session: BrowserSession = None,
    ) -> ActionResult:
        result = await _run_js(browser_session, JS_ENABLE_DATA_LABELS)
        if result.get("ok"):
            return ActionResult(extracted_content=f"Data labels: {result.get('action', 'done')}")
        return ActionResult(error=f"enable_data_labels failed: {result.get('error', 'unknown')}")

    logger.info("Registered Looker Studio custom actions: search_field_picker, replace_dimension, "
                "add_section, add_chart_in_section, set_chart_title, enable_axis_title, "
                "set_aggregation, set_section_stretch, scroll_to_style_option, "
                "enable_shadow, enable_data_labels, set_report_title")
    return controller
