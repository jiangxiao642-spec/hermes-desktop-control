# DirectShell 四阶段 UIA 激活 — 实测记录

## 来源
DirectShell (github.com/IamLumae/DirectShell, AGPL-3.0)
作者：Martin Gehrken

## 实测结果（2026-05-31）

| 应用 | 激活前 | 激活后 | 增益 | 备注 |
|------|-------|-------|------|------|
| OpenClaw Desktop | 10 | **2003** | 200× | 非 Store Electron，守护进程持久运行 |
| Claude Desktop (EXE) | 29 | **126** | 4× | winget 安装，需先登录 |
| Claude Desktop (Store) | 29 | 29 | 0 | AppContainer 外部 UIA 不可达 |
| 微信 Qt 5.15 | 2 | 2 | 0 | 纯 Qt 渲染，无 CEF 子窗口 |

## 关键发现

### 守护进程必须持久运行
单次 PowerShell 脚本退出后 FocusChanged handler 被 GC，`UiaClientsAreListening()` 恢复 FALSE，Chromium 立即缩回骨架。Tested: 单次 PS1 10→18，守护进程 10→2003。

### Claude Desktop 需要 EXE 版
- Store/MSIX 版安装路径 `C:\Program Files\WindowsApps\` — AppContainer 沙箱锁死外部 UIA
- winget 版 `winget install Anthropic.Claude` — 安装器类型 `exe`（Squirrel），无沙箱
- 安装路径：`C:\Users\<user>\AppData\Local\AnthropicClaude\claude.exe`
- **必须在登录后才暴露内容区 UIA 元素**——未登录状态只有 29 个窗口框架

### mouse_event 对 Electron 无效
Electron 忽略 `mouse_event` API。替代方案：`keybd_event Enter` 发送消息，或用 UIA 坐标 +键盘快捷键模拟点击。

## 脚本位置
- 守护进程：`D:\hermes\scripts\uia_daemon.ps1`
- 一次性激活：`D:\hermes\scripts\uia_activate.ps1`
- Bridge 工具（下次 session 可用）：`mcp_windows_bridge_uia_activate`
