# DeepSeek Web Chat — 2026-05-28 实测

## 页面信息

- URL: chat.deepseek.com（小鹿在Edge浏览器打开）
- 窗口: Edge, PID=4752, MainWindowTitle="DeepSeek - 探索未至之境"
- 页面初始状态：两个模式按钮"快速模式"(430,570)和"专家模式"(~540,570)，提示"使用专家模式开始对话"

## 输入机制

- 输入框: (134,657) 到 (948,810)，白色矩形
- 发送按钮: 蓝色圆形箭头图标，(894,757) 到 (928,791)
- **Enter键只换行，不发消息！** 必须鼠标点发送按钮

## 发送流程（正确）

```
1. 点击输入框 (500,730)
2. clipboard_write + ^v 粘贴消息
3. 点击发送按钮 (910,770) — 用mouse_event
```

## 发送流程（错误，踩过的坑）

```
- send_keys("{ENTER}") → 不发送，只换行 ← 跟Claude Desktop完全相反！
```

## Edge 激活方法（FindWindow失败时的替代）

```powershell
# FindWindow('MSEdgeWinClass', ...) 经常返回0
# 替代方案：通过Process获取MainWindowHandle
$proc = Get-Process -Id 4752
$hwnd = $proc.MainWindowHandle
ShowWindow($hwnd, 9)
SetForegroundWindow($hwnd)
```

## 未解决的问题

- "hi"发出去了但没有回复（可能需登录，或需先选模式）
- 后续完整消息粘贴到了输入框但页面没显示为已发送（发送按钮点击可能不准）
- 需进一步验证：登录状态检测、发送按钮的可靠坐标
