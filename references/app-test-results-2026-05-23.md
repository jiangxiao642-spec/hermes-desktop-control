# 应用实测结果 — 2026-05-23

desktop-control v3.5 全链路实战测试，五个应用。

## 记事本 (Win11, Notepad)

- **路径：** UIA
- **结果：** ✅ 全通
- **流程：** 启动→ShowWindow(5)+SetForegroundWindow→clipboard+^v→视觉验证
- **注意：** Win11 记事本 Edit 控件 ControlType 不是 Edit，是自定义类型。UIA 扫描找不到 Edit，但剪贴板粘贴不受影响。

## 文件资源管理器 (Win11, CabinetWClass)

- **路径：** UIA
- **结果：** ✅ 全通（需绕路）
- **流程：** 启动→UIA扫描(43项)→定位地址栏(autoId='TextBox', name='地址栏')→SetFocus→clipboard+^a^v+Enter→标题验证
- **坑：** 地址栏 ValuePattern.SetValue() 超时（Win11 新地址栏面包屑控件）。绕路：SetFocus + clipboard 粘贴。
- **验证：** 窗口标题从"主文件夹"变为"桌面"，确认导航成功。

## Edge 浏览器 (Chrome_WidgetWin_1)

- **路径：** 键盘优先
- **结果：** ⚠️ UIA 可读，SendKeys 不可靠
- **流程：** UIA 读到 URL 栏内容 ✅ | Ctrl+L→粘贴→Enter→UIA验证 ❌（URL未变）
- **根因：** Get-Process 返回 MainWindowHandle=0，ShowWindow/SetForegroundWindow 超时。Edge 多进程架构导致焦点不可靠。
- **可行：** UIA 读取页面状态（URL、文本）。写操作需先手动激活窗口。

## 设置 (Win11, ApplicationFrameWindow / SystemSettings)

- **路径：** UIA
- **结果：** ⚠️ 窗口在但无法激活
- **流程：** window_list 可见→SystemSettings 进程 MainWindowHandle=0→ShowWindow/SetForegroundWindow 超时
- **根因：** Win11 设置的 SystemSettings 进程不暴露有效窗口句柄，ApplicationFrameHost 作为壳窗口。

## 微信 (Qt, WeChatMainWndForPC)

- **路径：** SOM视觉看 / iLink协议动
- **结果：** ⚠️ iLink 通但联系人受限
- **流程：** window_list 可见→Win32 API 激活无效（Qt免疫）→iLink 发给小鹿成功→发给文件传输助手失败(ret=-3)
- **根因：** iLink bot 只能发给已建立会话的联系人。文件传输助手未在 context-tokens 中。
- **限流：** 连续 4 次 send_message 触发 rate limited (ret=-2)，需冷却 ~2 分钟。

## 规律

| 窗口类型 | UIA读 | UIA写 | Win32激活 | 推荐路径 |
|---------|-------|-------|----------|---------|
| Win32原生 (Notepad/Explorer) | ✅ | ✅ | ✅ | UIA |
| Chrome_WidgetWin_1 (Edge) | ✅ | ⚠️ | ❌ (hwnd=0) | UIA读 + 手动激活后键盘写 |
| WinUI3 (Settings) | ✅ | ❓未测 | ❌ (hwnd=0) | UIA读 |
| Qt (WeChat) | ❌ | ❌ | ❌ (免疫) | SOM看 + iLink动 |

## 关键教训

1. **MainWindowHandle=0 是 Win11 普遍现象** — Edge 和 Settings 都中招。不能靠 Get-Process 拿窗口句柄。
2. **Win11 新地址栏不兼容 ValuePattern.SetValue** — File Explorer 的地址栏是面包屑控件，SetValue 超时。剪贴板粘贴是可靠绕路。
3. **iLink 限流敏感** — 快速连续调用触发 ret=-2。失败后等 2 分钟再试。
4. **分类表是对的** — 不同应用必须走不同路径。UIA 一刀切会踩坑。
