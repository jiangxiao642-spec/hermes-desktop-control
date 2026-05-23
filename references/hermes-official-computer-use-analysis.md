# Hermes 官方 Computer Use 架构分析

**分析日期：** 2026-05-22（Hermes v0.14.0 → 1e71b7180 更新后）

## 核心结论

**Hermes 官方 computer_use 是 macOS only，Windows 上完全不可用。我们的 desktop-control 与它不在同一平台，不存在竞争或重复。**

## 官方架构

### 后端：cua-driver（macOS only）

`tools/computer_use/cua_backend.py` 第1行：`"""Cua-driver backend (macOS only)."""`

底层依赖 macOS 私有 SPI：
- `SLEventPostToPid` — 发送输入事件到指定进程
- `SLPSPostEventRecordTo` — 注入事件记录
- `_AXObserverAddNotificationAndCheckRemote` — 监听 Accessibility 通知

这些是 Apple 未公开的 SkyLight 框架 API，只能在 macOS 上运行。Windows/Linux 无等效机制。

### 操作模式

- **通过 MCP stdio 协议**与 cua-driver 通信
- **AX tree（Accessibility 树）**作为主要信息来源
- capture 时返回带编号的 UI 元素（SOM — Set-of-Mark）
- LLM 通过元素编号直接操作（`click element=5`），不依赖坐标
- 三种 capture 模式：`som`（标注）、`vision`（纯截图）、`ax`（纯树）

### vision_routing.py 的作用

**不是控制栈，不是状态机。** 仅做一件事：判断截图是直接发给主模型（多模态）还是先过辅助视觉模型转文字。

决策逻辑（`should_route_capture_to_aux_vision`）：
1. 用户显式配置了 auxiliary.vision → 走辅助视觉
2. 主模型 provider 不支持 tool-result 里带图片 → 走辅助视觉
3. 主模型 supports_vision=True → 走主模型直发
4. 其他情况 → 走辅助视觉（失败闭合）

这是一个**150行的 if-else**，不是操作层面的路由决策。

### 操作可靠性

- **无状态验证闭环**：每次操作是独立的，click 后不自动验证结果
- **无分层控制栈**：只有 AX tree 一条路径，没有 UIA/CDP/视觉 fallback
- **capture_after 参数**：可选在操作后截图返回，但 LLM 需自行判断成功与否
- **无重试机制**：操作失败直接返回 error JSON，不自动降级重试

### macOS AX tree 的优势

Apple Accessibility API 从 OS X 10.2 延续至今，覆盖率和一致性远好于 Windows UIA：
- 系统应用（Finder/Safari/Mail）全覆盖
- 第三方应用适配率高
- 元素 ID 稳定可靠

## 与我们的 desktop-control 对比

| 维度 | Hermes 官方 | 我们的 desktop-control v2.3 |
|------|------------|---------------------------|
| 平台 | macOS only | Windows only |
| 底层 | SkyLight SPI + AX tree | UIA + CDP + 视觉 |
| 控制栈 | 单层（AX tree） | 三层（CDP→UIA→视觉兜底） |
| 状态管理 | 无状态，每次独立 | UIA 状态机 + 四层验证 |
| 验证闭环 | 无自动验证 | UIA属性→pHash→OCR→云端vision |
| 重试策略 | 无 | 2次重试→降级→报结构化错误 |
| 元素定位 | 编号直接引用 | 多种策略（ClassName/ControlType/坐标） |
| Qt 支持 | 无（macOS 上 Qt 不多） | 视觉路径兜底（已验证可通） |
| Electron | AX tree 直读 | UIA（虚拟滚动需滚动拼接）+ CDP（非Store版） |

## 关键判断

**不是在比谁好——是在不同平台上解决不同问题。** 他们在苹果园里修路（AX tree 成熟稳定），我们在 Windows 沼泽里架桥（UIA 碎片化、Qt 盲区、Store 沙箱）。

官方方案在 macOS 上的 AX tree 方案比 Windows UIA 更成熟可靠——这是平台差异，不是架构差异。但官方方案对 Windows 零覆盖，我们的方案在 Windows 生态是独立开辟的。

## 对后续开发的启示

1. **不需要跟官方对齐架构**——他们不做 Windows，我们不做 macOS，互不干扰
2. **官方的 AX tree 直接引用元素方式**在 macOS 上优于坐标点击，但在 Windows UIA 上不可复制（UIA 元素 ID 不稳定）
3. **官方的无状态模式**在 macOS AX tree 可靠时可行，在 Windows 碎片化 UIA 上不行——我们的验证闭环是必须的
4. **如果未来 Hermes 支持 Windows computer_use**，很可能会是一个全新的 backend，不会复用 cua-driver 架构
