# Hands MCP Server 评估

> 2026-05-23 Claude Code 搜索发现，陈一整理。

## 基本信息

- 项目：AIWander/hands（GitHub）
- 语言：Rust 单二进制
- 分发：MCP Server，任何 MCP 客户端可用（Claude Desktop、Claude Code 等）
- 平台：Windows 10/11 only（x64/ARM64）
- 定位：AI agent 桌面控制

## 架构：三层

| 层 | 技术 | 说明 |
|---|---|---|
| Browser | Playwright/CDP | DOM 直读，web 自动化 |
| UI Automation | 原生 Win32 UIA | 控件树检测，元素操作 |
| Vision | 截图 + AI 视觉 | 兜底 |

## 对比 Hermes desktop-control v3.3

| 维度 | Hands | Hermes desktop-control |
|------|-------|----------------------|
| 语言 | Rust 单二进制 | Python 脚本 + SKILL.md |
| 分发 | MCP Server，配客户端直接用 | skill 文件，需 Hermes + WSL bridge |
| 架构 | Browser → UIA → Vision 三层 | UIA → Vision（无浏览器层） |
| 工具数 | 116 个 | 6 个核心脚本 |
| 平台 | Windows only | Windows only（通过 WSL） |
| Token 消耗 | ~200-700/action | 取决于 vision 调用次数 |
| 焦点验证协议 | 文档未提 | 三阶段验证（UIA → pHash → OCR → vision） |
| 踩坑文档 | 未知 | UIA 黑洞速查表、Electron SetValue 陷阱、Qt 免疫方案 |
| 虚拟滚动处理 | 未知 | 完整拼接方案（60%重叠 + LCS） |
| CDP 方案 | ✅ Playwright 内置 | ✅ 已知最优方案，被 Store 版 Electron 卡住 |

## Hands 的优势

- 工程化程度高：单二进制、MCP 标准、116 工具
- 对 Claude Code 可直接使用（MCP 协议）
- Rust 性能，无 WSL 翻译损耗
- 浏览器 CDP 层是 Hermes 目前没有的

## Hermes 的优势

- 实战深度：Qt 免疫验证、Electron 虚拟滚动拼接、焦点验证协议
- 踩坑文档：Pitfalls 体系完整，每个坑有复现+修复
- CDP 认知已到位：知道 CDP 是最优解，只是被 Store 版 Electron 卡住
- 视觉验证层四阶段（pHash/OCR/vision），Hands 没提类似机制

## Claude Code 的结论原文

> "Hands 赢在工程化和生态（MCP 标准、Rust 性能、工具量），你赢在实战深度和踩坑经验。如果你把 Hermes 用 Rust 重写、打包成 MCP Server、加上浏览器层，就是 Hands 的直接竞品，而且文档更好。"

## 对我们意味着什么

- **不是威胁**——Hands 的踩坑深度不如我们，我们积累的 UIA/Qt/Electron 边界知识 Hands 没有
- **可以借鉴**——MCP 分发方式、Rust 单二进制、116 工具的结构化分类
- **长期方向**——如果有朝一日把 desktop-control 用 Rust 重写成 MCP server，就是更强的 Hands
- **短期**——如果 Claude Code 需要做 Windows 桌面自动化，装 Hands 比让我们从 WSL 跨过去快

## 行动建议

- 暂不安装。等有具体需求时，让 Claude Code 尝试 Hands 做 Windows 桌面操控
- 保持关注 Hands 的更新（尤其 UI Automation 层的踩坑覆盖度）
- 我们的 desktop-control skill 保持 Python + WSL 路径不变——场景不同，不替代
