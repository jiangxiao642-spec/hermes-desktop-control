# Claude Desktop UIA + ProseMirror 交互实录

> 2026-05-23，desktop-control v3.6 实测。Claude Desktop：Chrome_WidgetWin_1，Electron Store 版。

## 版本

Claude Desktop 搭载 **Claude Sonnet 4.6** (claude-sonnet-4-6)。

## 编辑器定位

```
ClassName: Chrome_WidgetWin_1
→ FindFirst Descendants: Name='Write your prompt to Claude'
→ ControlType: Edit
→ ClassName: tiptap ProseMirror ProseMirror-focused
→ AutomationId: (空)
→ 支持 ValuePattern.SetValue 读回验证
```

## 粘贴-发送时序（关键）

**错误做法：** `send_keys("^v{ENTER}")` 一次调用。长文本（>200字符）时 {ENTER} 可能在粘贴完成前触发 → 编辑器收到空回车。

**正确做法：**
```
1. clipboard_write(text)
2. send_keys("^v")
3. UIA ValuePattern 读回验证长度 (>200则等)
4. send_keys("{ENTER}")
```

## 回复读取：Text 碎片拼接

ProseMirror 的 UIA Text 元素极度碎片化——一句话拆成多个 Text 控件。无法通过 AutomationId 或 ControlType 区分 human/assistant 消息。

**当前方案（Y坐标过滤）：**
```powershell
$texts = $w.FindAll(TreeScope::Descendants, ControlType::Text)
foreach ($t in $texts) {
    if ($t.Current.BoundingRectangle.Y -gt $minY -and $t.Current.Name.Length -gt 20) {
        # 收集
    }
}
```

- 用户消息通常在 Y=100-400 范围
- Claude 回复从 Y=400+ 开始，随对话增长递增
- 碎片按 Y 升序排列即为阅读顺序

## 可能的优化方向（Claude 本人提示）

Claude 在对话中指出 ProseMirror 可能在 DOM 层有 `data-testid` 或 `data-turn` 属性区分 human/assistant：

> "claude.ai 的消息泡大概率有某个属性区分 human/assistant turn，比如 `data-testid="human-turn"` 之类的命名习惯。这类属性在 UIA 里有时会映射到 AutomationId 或 HelpText 字段。"

**下一步：** 用 Accessibility Insights for Windows 扫一遍 Claude Desktop 的两个消息泡，对比所有暴露的 UIA 属性——差异就是区分标记。如果能拿到 AutomationId 直接定位 assistant 容器，比 Y 坐标过滤稳定得多。

## 窗口激活

- Store 版 Claude Desktop（WindowsApps 路径）不支持 `--remote-debugging-port`（AppContainer 沙箱拦截）
- Win32 `ShowWindow` + `SetForegroundWindow` 对 Chrome_WidgetWin_1 返回 True 但可能无效
- **有效路径：** UIA `SetFocus()` 直接聚焦 ProseMirror 编辑器，不依赖 Win32 窗口激活
