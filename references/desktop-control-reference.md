# Desktop Control Reference

> PowerShell代码块、完整示例、Pitfalls — 主文件见 SKILL.md

## UIA 路径：PowerShell 代码块

### 1. 定位控件

```powershell
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

# 1. 找窗口（ClassName + Name 组合最稳）
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ClassNameProperty, "Chrome_WidgetWin_1"
)
$candidates = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$win = $null
foreach ($c in $candidates) {
    if ($c.Current.Name -match "<窗口名关键词>") { $win = $c; break }
}

# 2. 找控件（ControlType + Name）
$ctrlCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.ControlType]::Edit
)
$edit = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $ctrlCond)
```

常用 ControlType：Edit, Button, Text, ListItem, TabItem, CheckBox, ComboBox, Document

### 2. 输入文本（统一剪贴板粘贴）

```powershell
# Step A: WSL侧先写入剪贴板
mcp_windows_bridge_clipboard_write(text="要发送的内容")

# Step B: UIA激活输入框
$edit.SetFocus()

# Step C: 粘贴（不受输入法/键盘布局影响）
mcp_windows_bridge_send_keys(keys="^v")
```

为什么不用 SetValue：Electron/React 应用里 SetValue 绕过前端状态，发送按钮判定为空。剪贴板粘贴触发原生 input 事件，前端状态同步。

### 3. 点击按钮（InvokePattern，不靠坐标）

```powershell
$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.ControlType]::Button
)
$buttons = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
foreach ($b in $buttons) {
    if ($b.Current.Name -eq "Send message") {
        $invoke = $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $invoke.Invoke()  # 不靠坐标，离屏按钮也能点
        break
    }
}
```

### 4. 窗口激活（前置必须）

```powershell
Add-Type @"
using System; using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string title);
}
"@
$h = [Win32]::FindWindow("Chrome_WidgetWin_1", $null)
[Win32]::SetForegroundWindow($h)
```

不激活直接 SetValue 可能 hang 30s+。

### 5. 读取状态（验证前置）

```powershell
# 读取 Edit 控件的当前文本
$vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$text = $vp.Current.Value

# 或读取 Text 控件
$text = $element.Current.Name
```

### 6. 验证闭环

```
执行操作
   ↓
读取控件状态（实际文本/是否存在）
   ↓
对比预期：文本是否包含目标内容？
├── 匹配 → DONE ✅
├── 不匹配 → retry（最多2次）
│   └── 2次全失败 → FAIL: [操作] [预期] [实际]
```

---

## 完整示例：给 OpenClaw 发消息（UIA 路径）

```
# 步骤0：策略决策
目标：OpenClaw → Electron → UIA路径 ✅

# 步骤1U：定位
run_powershell:
  $root = [AutomationElement]::RootElement
  $cond = PropertyCondition(ClassNameProperty, "Chrome_WidgetWin_1")
  $candidates = $root.FindAll(Descendants, $cond)
  $win = 匹配 "OpenClaw" 的
  $edit = $win.FindFirst(Descendants, PropertyCondition(ControlType.Edit))

# 步骤2U：执行
$edit.SetFocus()
clipboard_write("这是一条测试消息")
send_keys("^v")

# 步骤3U：读取验证
$vp = $edit.GetCurrentPattern(ValuePattern.Pattern)
$text = $vp.Current.Value
# $text 包含 "这是一条测试消息" → 内容已进入输入框 ✅

# 步骤2U-2：发送
找到 "Send message" button
InvokePattern.Invoke()

# 步骤4U：发送后验证
等待800ms
UIA扫描窗口文本 → 确认 "这是一条测试消息" 出现在聊天区域 → DONE ✅
```

---

## 完整示例：右键桌面（视觉路径）

```
# 步骤0：策略决策
目标：Desktop空白区 → 无UIA树 → 视觉路径

# 步骤1V：感知
screenshot(grid=true)
vision: "Find blank desktop area. Report X,Y from grid."
  → "Desktop blank area, (900, 900)"

# 步骤2V：执行
mouse_action.py right-click 900 900

# 步骤3V：验证
screenshot()
vision: "Is there a right-click context menu visible? Read the menu items."
  → "Yes, menu visible with items: View, Sort by, Refresh, New, ..." → DONE ✅
```

---

## 完整示例：给 Win11 记事本输入文本（UIA 路径，2026-05-19 实测通过）

```
# 步骤0：策略决策
目标：Notepad → Win11版本是WinUI3 → UIA路径 ✅

# 步骤1U：定位（注意Win11 Notepad结构不同！）
run_powershell:
  Add-Type UIAutomationClient, UIAutomationTypes
  $root = [AutomationElement]::RootElement
  # Win11 Notepad: Notepad窗 → NotepadTextBox(Pane) → RichEditD2DPT(Document)
  $cond = PropertyCondition(ClassNameProperty, "RichEditD2DPT")
  $doc = $root.FindFirst(Descendants, $cond)
  → Name="文本编辑器" Class="RichEditD2DPT" ✅

# 步骤2U：执行（SetFocus + 桥接send_keys粘贴）
$doc.SetFocus()
clipboard_write("测试文本")
send_keys("^v")  # 用bridge的send_keys，不是PS的SendKeys！

# 步骤3U：读回验证
$vp = $doc.GetCurrentPattern(ValuePattern.Pattern)
$vp.Current.Value 包含 "测试文本" → VERIFY_PASS ✅
```

---

## 完整示例：给 Claude Desktop 发消息（UIA 路径，2026-05-19 实测通过）

```
# 步骤0：策略决策
目标：Claude Desktop → Electron → UIA 路径 ✅

# 步骤1U：定位（ProseMirror 富文本编辑器）
run_powershell:
  Add-Type UIAutomationClient, UIAutomationTypes
  $root = [AutomationElement]::RootElement
  # Claude 窗口: Chrome_WidgetWin_1, Name="Claude"
  $cond = PropertyCondition(NameProperty, "Claude")
  $win = $root.FindFirst(Descendants, $cond)
  # 输入框: ControlType.Edit, Name="Write your prompt to Claude"
  $editCond = PropertyCondition(ControlTypeProperty, ControlType.Edit)
  $edit = $win.FindFirst(Descendants, $editCond)
  → Name="Write your prompt to Claude" Class="tiptap ProseMirror" ✅

# 步骤2U：执行
$edit.SetFocus()
clipboard_write("嘿Claude，我是陈一...")
send_keys("^v")  # ProseMirror 支持 ValuePattern，但粘贴触发前端事件最稳

# 步骤3U：读回验证
$vp = $edit.GetCurrentPattern(ValuePattern.Pattern)
$vp.Current.Value 包含 "陈一" → VERIFY_PASS ✅

# 步骤2U-2：发送
send_keys("{ENTER}")  # Claude Desktop 用 Enter 发送，无独立 Send 按钮

# 步骤4U：发送后验证
等待 5-8s（Claude 推理延迟）
UIA 扫描 Text 元素 → Y≈394 发现 "看到了，陈一。消息收到" → DONE ✅
```

---

## 完整示例：给 Claude Desktop 发消息（简化版 — Electron/ProseMirror）

```
# 步骤0：Claude Desktop → Electron → UIA路径

# 步骤1U：定位
ClassName="Chrome_WidgetWin_1" + Name="Claude" → 窗口
ControlType.Edit → ProseMirror 编辑器
  Name="Write your prompt to Claude"
  Class="tiptap ProseMirror"

# 步骤2U：执行
$edit.SetFocus()
clipboard_write("消息内容")
send_keys("^v")        # ProseMirror 也支持 ValuePattern，但粘贴更稳
send_keys("{ENTER}")    # 回车发送

# 步骤3U：发送前验证
$vp = $edit.GetCurrentPattern(ValuePattern.Pattern)
$vp.Current.Value 包含 "消息内容" → VERIFY_OK

# 步骤4U：发送后验证
UIA扫描 ControlType.Text → 筛选 Y 坐标在聊天区范围 → Claude 回复可见 ✅
```

---

## Qt 应用视觉路径（UIA 全盲时的标准方案，2026-05-19 微信实测）

Qt 自绘控件 UIA 树只有一个壳。不用 OCR 硬找按钮——用**视觉锚点 + 相对布局推断**。

### 原则

- 不找输入框本身，找发送按钮图标/聊天气泡等**稳定锚点**
- 根据布局关系**推断**输入区域位置（发送按钮左上 N 像素）
- 点击推断区域 → Ctrl+V → 视觉验证
- 所有坐标用**窗口内相对坐标**，不靠屏幕绝对坐标

### 步骤

1. **获取窗口矩形**（win32gui.GetWindowRect 或 UIA BoundingRectangle）→ 所有后续坐标以此为原点
2. **截图窗口区域**（不是全屏）→ 缩小 OCR 搜索范围
3. **找锚点**：发送按钮图标（优先，比文字稳）、工具栏图标、聊天气泡区
4. **推断输入区**：`input_y = send_btn.y - 120, input_x = send_btn.x - 500`
5. **点击推断区域** → clipboard_write → send_keys ^v → {ENTER}
6. **视觉验证**：截图确认消息出现在聊天区

### 微信实测数据（2026-05-19）

- 窗口全屏 1707×1067，输入区点击坐标 (900, 950) 可用
- 锚点：发送按钮在输入框右下，聊天气泡区域在上方
- 三轮消息全部送达，回复 OCR 可读

---

## Pitfalls

### Claude Desktop 使用 ProseMirror，ValuePattern 可用（v2.0 实测）
Claude Desktop 输入框是 `tiptap ProseMirror`（富文本编辑器），Class 含 "ProseMirror-focused"。实测 ValuePattern 读写均可用——但粘贴比 SetValue 更安全（SetValue 可能不触发 Slate/ProseMirror 内部状态更新）。发送方式：Enter 键，无独立 Send 按钮。

### Win11 记事本是 WinUI3，不是经典 Edit 控件（v2.0 实测）
Win11 Notepad 的 UIA 树是：Notepad → NotepadTextBox(Pane) → RichEditD2DPT(Document, Name="文本编辑器")。不能按 ClassName="Edit" 找。正确做法：直接按 ClassName="RichEditD2DPT" 全局搜。ValuePattern 读写均可用。详见 `windows-bridge-playbook` skill 的 `references/win11-notepad-uia-anatomy.md`。

### PowerShell SendKeys 在桥接会话不可用（v2.0 实测）
`[System.Windows.Forms.SendKeys]::SendWait` 在 run_powershell 中报 TypeNotFound。改用 bridge 的 `mcp_windows_bridge_send_keys` 工具，它在 Windows 侧本地执行按键。

### Qt 应用 UIA 全盲（微信实测，2026-05-19）
微信 PC 版 ClassName=`Qt51514QWindowIcon`，UIA 树只露一层壳（1个 Pane，0个 Edit，0个 List，0个子控件）。**Qt 自绘控件完全不走 Windows Accessibility。** 应对：直接走视觉兜底路径。截图定位输入区 → mouse_action click → clipboard_write + ^v → {ENTER}。Qt 应用输入区坐标依赖窗口状态——最大化/窗口化/拖拽后需重新定位。

### Store 版 Electron 开不了 CDP（Claude Desktop 实测，2026-05-19）
Claude Desktop 为 Microsoft Store 打包（WindowsApps 路径，AppContainer 沙箱）。`--remote-debugging-port` 参数被运行时吞掉，`ELECTRON_REMOTE_DEBUGGING_PORT` 环境变量无效。结论：**不浪费时间去搞偏门。等换非 Store 版再开 CDP。** Claude Desktop 使用 tiptap ProseMirror 富文本编辑器，非标准 Edit。但 ValuePattern 可用——读写均正常。粘贴路线（clipboard_write + ^v）比 SetValue 更稳（触发 ProseMirror 内部状态同步）。发送用 {ENTER}，无独立 Send 按钮。

### 虚拟滚动（Electron 聊天应用，GPT-5.5 确认）
Claude Desktop、Discord、Slack 等 Electron 聊天应用使用虚拟列表（react-window/react-virtualized）。UIA 的 Accessibility Tree 只反映当前 DOM 节点——滚出视口的消息被 DOM 删除，UIA 读不到。读完整聊天记录需：读取可见区 → hash 去重 → 向上滚动 → 再读 → 拼接。代码块在滚动重排中容易碎裂——拼接后需手动校准缩进。

### 虚拟滚动：视口重叠拼接方案
1. 读取当前 Viewport 所有 Text → `{text, y, height}`
2. 按 Y 排序，合并相邻行（y差 < 行高×0.6 = 同一行）
3. **小步滚动** 60% 视口高度（确保上下屏重叠）
4. 重叠区匹配：上一屏最后 N 行 vs 下一屏前 N 行，找最长公共子串
5. 注意 normalize whitespace（多空格压缩、去尾空格、统一换行）再匹配——exact match 会因缩进变化炸

**代码块特殊处理：** 代码行被拆成多个 Text node（甚至 token 级），别用 Text 粒度拼接。按**垂直区域连续性**识别整块（连续 Y + 相近行高 + 等宽字体），整块拼接而非逐行。核心原则：重建的是 Layout/Paragraph 结构，不是字符串拼接。

### CDP 是 Electron 内容读取的最优方案，但 Store 版不可用（GPT-5.5 确认）
读取 Electron 应用的完整 DOM 应走 CDP（Chrome DevTools Protocol）——`Runtime.evaluate` 直接拿 `document.body.innerText`，不经过 Accessibility Tree 翻译层。但 Windows Store 打包的 Electron 受 AppContainer/MSIX 沙箱限制。结论：Store 版走 UIA 拼接；CDP 等换非 Store 版再切。

### ^v{ENTER} 可合并为一次 send_keys 调用（v2.0 实测）
`send_keys("^v{ENTER}")` 在同一个 bridge 调用里粘贴+回车，减少一次往返。注意：粘贴内容超 500 字时分开调用——先 ^v、读回验证、再 {ENTER}，避免粘贴未完成就回车。

### SetValue 绕过 React 状态（v1.x 已知，v2.0 不再使用）
Electron 应用的 SetValue 只改 DOM 不触发 React onChange → 发送按钮判定输入为空。v2.0 统一使用 clipboard_write + ^v，此问题已消除。

### 未激活窗口直接 SetValue 会 hang
UIA 在窗口未激活时 SetValue 可能阻塞 30s+。步骤1U 必须先 `SetForegroundWindow`。

### 离屏按钮
Electron 应用可能将按钮放在屏幕外（如 OpenClaw Send 按钮 X=2415, Y=1424 在 1707×1067 屏幕上）。UIA InvokePattern.Invoke() 不依赖坐标，直接生效。

### 浏览器页面元素点击不可靠（v1.3 已知）
JS 渲染元素用 mouse_event 点击失败率高。浏览器任务强制走键盘路径——Ctrl+L 导航、Tab 切换、Enter 激活。

### vision 坐标漂移（v1.3 已知）
密集页面小目标坐标方差可达 ±700px。视觉路径必须走精确定位（200×200 裁剪二次确认），不可跳过。

### DPI 缩放
步骤0 检测 DPI（[D]::Scale()），scale≠1.0 时所有视觉坐标 × scale。

### 文本输入铁律补充
SetValue 绕过 React/Electron 状态，SendKeys 打字受输入法影响，clipboard_write + ^v 是唯一全局可靠方案。
