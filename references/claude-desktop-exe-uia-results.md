# Claude Desktop UIA — EXE 版安装与激活实测 (2026-05-31)

## 背景
Claude Desktop 有两种安装方式：
- **MSIX/Store 版** → AppContainer 沙箱 → 外部 UIA 不可达（骨架 ~29 元素）
- **EXE 版（Squirrel 安装器）** → 无沙箱 → 登录后暴露 ProseMirror 内容区（126 元素）

## EXE 版安装
```
winget install Anthropic.Claude
```
安装路径：`C:\Users\<user>\AppData\Local\AnthropicClaude\claude.exe`

## UIA 实测数据
- 未登录：29 元素（窗口框架+标题栏按钮）
- 已登录：126 元素（含输入框 "Write your prompt to Claude"、发送按钮 "Send message"、聊天消息 Text 元素）
- 激活后变化：0（126 稳如——Claude 的 Electron 构建不响应 SPI_SETSCREENREADER）
- 对比 OpenClaw：10→2003（200×，因为 OpenClaw 的 Chromium 响应激活）

## 已确认可用操作
| 操作 | 方法 | 结果 |
|------|------|------|
| 读消息 | UIA Text 元素 Name 属性 | ✅ |
| 写输入框 | clipboard^v + UIA SetFocus | ✅ |
| 点击发送 | keybd_event Enter（mouse_event 无效） | ✅ |
| 读按钮坐标 | UIA BoundingRectangle | ✅ 65 个按钮全部可读 |
| InvokePattern 点击 | — | ❌ Electron 不暴露 |

## 键鼠操作选型
- **打字** → clipboard^v（不变）
- **发送** → keybd_event Enter（非 mouse_event click）
- **定位** → UIA FindFirst + BoundingRectangle 中心坐标

## 守护进程
`uia_daemon.ps1` 对 Claude Desktop 有效但元素数不变（126 稳）。主要价值在 OpenClaw（保持 2003 元素）。
