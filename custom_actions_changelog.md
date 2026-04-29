# LookerStudioAgent v3 — Custom Actions 設計紀錄

> 更新日期：2026-04-08
> 分支：`subagent_workload`

---

## 背景與動機

LookerStudioAgent 使用 browser-use 框架驅動 Gemini 模型，透過 CDP（Chrome DevTools Protocol）操作瀏覽器自動建立 Looker Studio 儀表板。

在實際運行的 169 步與 112 步 log 分析中，發現以下核心問題：

| 失敗模式 | 浪費步驟 |
|---|---|
| Field picker 搜尋失敗（虛擬捲動未渲染） | 12+ 步/次 |
| Agent 點選錯誤的 Dimension chip | 每個 chart 都發生 |
| `add_section` 將新區段插入頂部而非底部 | 導致後續所有 chart 位置錯誤 |
| Style panel 元素不在可視範圍內 | 每個樣式操作需要額外捲動步驟 |
| Canvas 標題輸入至錯誤元素（text box 被汙染） | 最後步驟失敗 |
| 無參數 action 被 Gemini 附加 `_placeholder` 造成 Pydantic 驗證失敗 | agent 強制終止 |

**根本原因**：LLM 在 context compaction 後容易忘記操作規則，且部分 DOM 互動（點擊特定 chip、捲動 Style 面板內部捲軸、找到正確的新增按鈕）本質上對 LLM 推理不穩定。

**解決策略**：將高失敗率的 UI 互動封裝為**確定性 JavaScript Custom Actions**，讓 agent 直接呼叫，而非自行推理點擊位置。

---

## Custom Actions 完整清單

所有 action 定義於 `scripts/looker_studio_actions.py`，透過 `register_looker_actions(controller)` 註冊至 browser-use Controller。

### 1. `search_field_picker(field_name)`
**用途**：在已開啟的 field picker 中搜尋並選取欄位。

**解決問題**：Field picker 使用 `cdk-virtual-scroll-viewport` 虛擬捲動，未渲染的項目無法被 agent 點選；且直接在搜尋框輸入文字時 Angular change detection 不觸發，導致「No results」。

**JS 關鍵技術**：
- 使用 `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` 觸發 Angular 原生 change detection
- 等待 500ms 讓虛擬捲動過濾結果後再點擊

---

### 2. `replace_dimension(dim_index)`
**用途**：點擊 Setup tab 中第 `dim_index` 個 dimension chip，開啟 field picker 以取代現有欄位。

**解決問題**：Agent 每次都點選「Add dimension」按鈕而非現有 chip，導致 chart 累積多餘的欄位而非取代預設欄位。

**JS 關鍵技術**：
- 過濾掉 metric 容器內的 chip（避免誤點 metric chip）
- 點擊 chip 的 label 部分而非 aggregation icon

---

### 3. `add_section()`
**用途**：在最後一個區段**下方**新增空白區段。

**解決問題**：原本使用 `document.querySelector('.add-section-button')` 回傳 DOM 中**第一個**按鈕，而 Looker Studio 在每個區段之間都有一個「新增區段」按鈕，導致新區段被插入至頂部。

**JS 關鍵修正**：
```js
// 錯誤：取第一個
document.querySelector('.add-section-button')

// 正確：取最後一個
var btns = document.querySelectorAll('.add-section-button');
btns[btns.length - 1].click();
```

**無參數 action 相容性**：Gemini 呼叫無參數 action 時會附加 `{"_placeholder": ""}` 導致 Pydantic 驗證失敗使 agent 強制終止。修正方式：加入 `_placeholder: str = Field(default="", description="unused")` 參數接收此值。

---

### 4. `add_chart_in_section(section_index)`
**用途**：點擊指定區段內的「新增圖表」按鈕，開啟圖表選擇器。

**解決問題**：區段可能處於「空白 placeholder」或「已有圖表」兩種狀態，按鈕的 class 不同，agent 容易混淆。

**JS 邏輯**：依序嘗試 `.placeholder-add-chart-button` 和 `.add-chart-button`。

---

### 5. `set_chart_title(title_text)`
**用途**：在 Style tab 啟用「Show title」開關並設定標題文字。

**解決問題**：「Show title」開關在 Style tab 頂部，但 context compaction 後 agent 忘記需要先捲動至此，改用通用 `scroll` action（無法捲動面板內部捲軸）。

**JS 關鍵技術**：`scrollIntoView({block:'center'})` + Angular native input setter

---

### 6. `enable_axis_title(axis)`
**用途**：啟用 X 軸（`axis='x'`）或 Y 軸（`axis='y'`）標題。

**解決問題**：「Show axis title」開關需先確認「Show axes」開關已啟用，且兩個軸的開關 aria-label 相同（需用 `querySelectorAll()[index]` 區分）。Agent 常忘記先啟用前置條件。

**JS 邏輯**：先檢查並啟用 `Show axes`，再用 index `0`（X 軸）或 `1`（Y 軸）定位正確開關。

---

### 7. `set_aggregation(aggregation_type)`
**用途**：設定 metric 的 aggregation 類型（COUNT、SUM、AVG 等）。

**解決問題**：Agent 混淆 chip 的「文字區域」（開啟 field picker）與「aggregation icon」（開啟 edit panel）兩個點擊目標。

---

### 8. `set_section_stretch(section_index)`
**用途**：將指定區段的版型設為 Stretch（圖表等寬填滿）。

**解決問題**：需先開啟區段的 style menu，再點擊 Stretch 選項，兩步操作封裝為一個 action。

---

### 9. `scroll_to_style_option(aria_label)`
**用途**：將 Style 面板捲動至指定元素後再進行互動。

**設計動機**：Style 面板有自己的**內部捲軸**，browser-use 的通用 `scroll` action 只能捲動頁面，無法捲動面板內部。所有 Style tab 手動操作（顏色選取、字型大小、圖例設定等）都需要先呼叫此 action。

**JS 三層搜尋邏輯**：
1. 精確 aria-label 匹配
2. 部分 aria-label 匹配（`indexOf`）
3. 可見文字內容匹配（label / span / div 的 `textContent`）

**Playbook 套用範圍**：
| Procedure | 捲動錨點 |
|---|---|
| `style_set_color` | `'Series'` |
| `style_set_font_size` | `'Font size'` |
| `style_set_font_color` | `'Font color'` |
| `style_set_legend_position` | `'Display legend'` |
| `style_toggle_compact_numbers` | `'Compact numbers'` |
| `style_set_background_color` | `'Add border shadow'` |
| `others`（通用） | 以 `{others}` 指令本身作為錨點 |

---

### 10. `enable_shadow()`
**用途**：啟用「Add border shadow」開關（含 `scrollIntoView`）。

---

### 11. `enable_data_labels()`
**用途**：啟用「Show data labels」開關（含 `scrollIntoView`）。

---

### 12. `set_report_title(title_text)`
**用途**：設定 canvas 上的報表標題（「Add report title」佔位文字）。

**解決問題**：Canvas 標題的 DOM 分為 `ng2-textbox-viewer`（唯讀顯示）和 `ng2-textbox-editor`（`contenteditable=true` 可編輯）兩個節點。Agent 將文字輸入至 viewer 節點，導致按鍵事件流向仍在 focus 的 footer text box，汙染 footer 內容。

**JS 修正**：`dblclick` viewer 啟動 editor → `execCommand('selectAll')` → `execCommand('insertText', false, titleText)`。

---

## 架構設計原則

### Compaction 韌性三層保護

| 層級 | 內容 | 原理 |
|---|---|---|
| **System Prompt** | 一行規則：`When a task step says "Use <action_name>", call that custom action directly` | 從不被 compaction 壓縮 |
| **todo.md 規則標頭** | `generate_todo()` 注入完整規則表，每步都透過 `<todo_contents>` 顯示 | 每步重新注入，compaction 後仍可見 |
| **Custom Actions 本身** | 確定性 JS，agent 不需記得「如何操作」，只需記得「呼叫哪個 action」 | 消除「遺忘規則」的根本問題 |

### Idempotency 設計
所有 toggle action 在點擊前先檢查 `classList.contains('mdc-switch--checked')`，避免重複點擊導致關閉。

### Angular 相容性
所有文字輸入使用 `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` 觸發原生 setter，確保 Angular change detection 正確響應。

---

## 已解決 vs 待觀察

| 問題 | 狀態 |
|---|---|
| Field picker 搜尋失敗 | ✅ 已解決（`search_field_picker`） |
| Agent 點選錯誤 dimension chip | ✅ 已解決（`replace_dimension`） |
| `add_section` 插入至頂部 | ✅ 已解決（`querySelectorAll` 取最後一個） |
| Style panel 捲軸問題 | ✅ 已解決（`scroll_to_style_option`） |
| Canvas 標題輸入至錯誤元素 | ✅ 已解決（`set_report_title`） |
| 無參數 action Pydantic 驗證失敗 | ✅ 已解決（`_placeholder` 參數） |
| `set_aggregation` edit panel 未開啟 | 🔄 待下次 run 驗證 |
| `replace_metric` 尚未實作 | ⏳ 待實作 |
| `rename_report`（editor 標題）尚未實作 | ⏳ 待實作 |
