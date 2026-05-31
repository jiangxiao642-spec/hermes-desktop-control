---
name: desktop-control
description: "v3.9 — 三元验证（PASS/FAIL/UNCERTAIN）+ Anchor心跳 + UIA守护进程。Win32/WinUI3/Electron/Qt全覆盖。"
---

# Desktop Control Skill v3.9

> **WHAT（边界）：** Windows 桌面 GUI 操控栈——UIA 主通道 + 视觉兜底。**覆盖** Electron/Win32/WinUI3 应用的精确操控——读消息、写字、点击、截图。**不覆盖** Qt 应用的 UIA 操控（走视觉兜底）、应用内部逻辑、业务流程编排。这个 skill 只管"怎么操控桌面"，不管"操控来完成什么任务"。

**v3.9: 三元验证（PASS/FAIL/UNCERTAIN）+ Anchor 心跳（操作前确认关键控件存活）。**

## 操作流程

**🆕 UIA 激活前置（v3.8）：** 目标为 Electron/Chromium 应用时，**先跑** `mcp_windows_bridge_uia_activate(pid=<目标PID>)` 或启动 `uia_daemon.ps1` 持久守护。四阶段激活后元素数可暴增（OpenClaw 实测: 10→2003，200×）。⚠️ Store 版应用（Claude Desktop AppContainer）外部 UIA 不可达——激活无效。**关键：handler 必须持久存活——单次 PS1 退出后 UiaClientsAreListening() 恢复 FALSE，Chromium 立即缩回骨架。** 详见 `references/directshell-uia-activation.md`。

**🆕 三元验证 + Anchor 心跳（v3.9，Claude 协作）：**
- 验证不再是 pass/fail 二元——多了 **UNCERTAIN** 状态。UNCERTAIN 自动升级验证层（UIA→OCR→vision），不手动判断。
- 每轮操作前先跑 **anchor 心跳**——确认关键控件（发送按钮/输入框）还在，不等操作失败才发现窗口崩溃。
- `VerifyResult` 和 `AnchorHeartbeat` 类已加入 `scripts/robustness.py`。anchor 检测通过 UIA 守护进程的 snap 文件判断——`Total elements` 骤降 = 窗口异常。

```
收到 GUI 任务
├── 0. 查应用分类表 → 确定推荐路径（UIA / SOM视觉 / iLink / 键盘）
├── 1. 护盾检查
│   ├── health.can_operate()? → STALLED? → 通知用户
│   ├── breaker.allow_call()? → OPEN? → 降级非vision路径
│   └── env.capture(w, h, dpi) → changed? → 清SOM缓存
├── 2. SOM 标注
│   ├── UIA 可用 → PowerShell 扫描 UIA 树 → 编号元素列表 [1],[2]...
│   └── UIA 不可用 → 截图 + vision 标注可交互区域
├── 3. 交叉验证（UIA+vision 都可用时）
│   └── 匹对两边结果 → 高置信直接操作，未验证先裁剪确认
├── 4. 每步执行前 checkpoint（v3.6）
│   └── safepoint.checkpoint(phash, window_class, action, description)
├── 5. 执行操作
│   ├── UIA + AutomationId → InvokePattern / ValuePattern
│   ├── UIA + 无 AutomationId → 按 bounds 中心坐标
│   └── 视觉模式 → 按标注坐标
└── 6. 验证闭环
    ├── Tier 0: UIA 属性读回 (~0ms)
    ├── Tier 1: 区域 pHash (~1ms)
    ├── Tier 2: 本地 OCR (~500ms)
    └── Tier 3: 云端 vision (3-5s 兜底)
    → 成功 → health.record_success(), breaker.record_success()
    → 失败 → safepoint.rollback(reason)
        ├── can_recover() → 回到上一安全点，换恢复路径重试
        └── !can_recover() → DESKTOP_CONTROL_FAILED: [窗口] [操作] [原因]
```

## 应用 UIA 覆盖矩阵（v3.9 实测）

| 应用 | UIA 元素 | 状态 | 备注 |
|------|---------|------|------|
| OpenClaw Desktop | 2003 | ✅ 全通 | 非 Store Electron，守护进程激活后全树暴露 |
| Claude Desktop (winget EXE) | 126 | ✅ 可用 | `winget install Anthropic.Claude`（安装器类型 exe）；**必须登录**后才暴露 ProseMirror 输入框和消息内容。未登录时 29 骨架；mouse_event 忽略，用 keybd_event Enter 发送 |
| Claude Desktop (Store/MSIX) | 29 | ❌ | AppContainer 沙箱锁死外部 UIA |
| 微信 (Qt 5.15) | 2 | ❌ | 纯 Qt 渲染，无 CEF 子窗口。走视觉路径 |
| VS Code / Discord | 预估千级 | ✅ | Electron，与 OpenClaw 同类 |

## 键鼠操作铁律（Electron）

- **粘贴文本：** clipboard + `^v`（SetValue 绕过 React 状态，发送为空）
- **发送消息：** `keybd_event Enter` — ✅ 有效
- **点击按钮：** `mouse_event` — ❌ Electron 忽略。用 UIA 读 BoundingRectangle 中心坐标 + `Cursor.Position` + `SendKeys.SendWait('{ENTER}')` 或键盘快捷键替代
- **激活窗口：** `ShowWindow(9)` + `SetForegroundWindow`（EXE 版有效）

> ⚠️ **Win11 注意：** Edge 和 Settings 的 Get-Process 返回 MainWindowHandle=0，ShowWindow/SetForegroundWindow 无效。Chrome_WidgetWin_1 和 WinUI3 应用不靠 Process 拿句柄——用 UIA RootElement.FindFirst 按 ClassName 定位。

```
拿到目标窗口 ClassName → 查下表
├── 命中 → 直接走推荐路径
└── 未命中 → 通用决策树（UIA先试 → 失败则视觉兜底）
```

| 应用 | ClassName | 推荐路径 | 原因 |
|------|----------|---------|------|
| 记事本 (Win11) | Notepad | **UIA** | 控件清晰，有 AutomationId |
| 微信 (Qt) | WeChatMainWndForPC | **SOM看 / iLink动** | Qt免疫Win32点击。状态读用SOM，消息发用iLink |
| Qt 应用通用 | Qt5QWindow* 等 | **SOM看 / iLink动** | Win32 API对Qt无效。只读不写 |
| Claude Desktop (winget EXE) | Chrome_WidgetWin_1 | **UIA** | winget 安装版 126 元素，ProseMirror 输入框+消息可读写；**必须登录**后才暴露内容。用 keybd_event Enter 发送 |
| Claude Desktop (Store/MSIX) | Chrome_WidgetWin_1 | **视觉** | AppContainer 沙箱锁死外部 UIA，29 骨架。走截图+SOM |
| Edge 浏览器 | Chrome_WidgetWin_1 | **键盘优先** | Ctrl+L/Tab/Enter，不点页面元素 |
| DeepSeek Web | Chrome_WidgetWin_1 | **键盘+SOM** | Enter不发消息！必须点发送按钮(蓝色圆形箭头)。可能需先登录。Edge激活用Get-Process MainWindowHandle+FOCUS脚本 |
| VS Code | Chrome_WidgetWin_1 | **UIA** | Electron，控件树完整 |
| 文件资源管理器 | CabinetWClass | **UIA** | Win32 标准控件 |
| 任务管理器 | TaskManagerWindow | **UIA** | Win32，列表可读 |
| 设置 (Win11) | ApplicationFrameWindow | **视觉** | WinUI3 Store 应用，AppContainer 隔离，外部 UIA 不可达（2026-05-31 实测） |
| 画图 | ApplicationFrameWindow | **UIA** | WinUI3 |
| Office 系列 | _WwG / OpusApp 等 | **UIA** | Win32 自有控件体系 |
| OpenClaw Desktop | Chrome_WidgetWin_1 | **UIA** | 守护进程激活后 2003 元素，全树可读写 |

## 操作指令格式（think-act-verify）

**模板：**
```
操作: click element=7 (Button "发送")
预期: 消息列表底部出现新条目，内容以"你好"开头
验证: OCR读消息列表最后一个气泡 → 文本包含"你好" → 匹配=通过，不匹配=重试
失败: retry 1次 → 仍失败则降级为坐标点击(元素#7的bounds中心) → 再失败报DESKTOP_CONTROL_FAILED
```

**各操作默认验证锚点：**

| 操作 | 预期 | 验证方法 | 失败处理 |
|------|------|---------|---------|
| click 按钮 | 按钮变色/消失/新元素出现 | pHash变→OCR读新元素 | retry→坐标降级→vision兜底 |
| type 输入 | 输入框文本=预期 | UIA ValuePattern 或 OCR | 重输→全选替换→报FAILED |
| 打开应用 | 窗口出现(ClassName匹配) | window_list | 重试→报FAILED |
| 导航/切换 | 页面标题/URL变化 | UIA NameProperty | retry→截图+vision |
| 滚动 | 新内容可见 | 重新SOM扫描→对比 | retry 1次 |

**关键原则：**
- 预期必须可验证。不说"操作成功"，说"按钮Text属性变成'已发送'"
- 验证优先级：UIA属性 > OCR > pHash > 云端vision
- 失败导向明确："降级到X"或"报FAILED含原因"
- UIA 路径操作自带闭环——视觉路径操作必须带 think-act-verify

**闭环铁律：API响应 ≠ 终端结果验证。**
- 任何"闭环完成"声明必须跟可验证证据：截图/OCR读回/窗口状态变更
- 协议通道（iLink）发消息后，验证是**截图确认消息出现在聊天窗口**，不是读API返回值

## 操作接口（element 优先）

| 操作 | 新方式 (v3.0+) |
|------|---------------|
| 点击按钮 | `click element=7` (UIA: InvokePattern; 视觉: bounds中心) |
| 输入文本 | `type element=3 text="你好"` (先点输入框→clipboard+^v) |
| 读取内容 | `read element=5` (UIA: ValuePattern; 视觉: OCR区域) |

**element 索引解析优先级:**
1. UIA + automation_id 存在 → 直接按 AutomationId 定位
2. UIA + 无 automation_id → 按 bounds 中心坐标
3. 视觉模式 → 按标注 bounds 坐标

## 文本输入铁律

| 做法 | 用 | 为什么 |
|------|-----|--------|
| clipboard_write + ^v | **是** | 不受输入法/键盘布局影响 |
| send_keys 逐字打 | 否 | 中文输入法状态一乱全崩 |
| SetValue (Electron) | 否 | 绕过React状态，发送判定为空 |

**⚠️ send_keys 时序坑：** `^v{ENTER}` 合并到一次 send_keys 调用时，长文本（>200字符）的粘贴和回车之间没有间隔，{ENTER} 可能在剪贴板写入完成前触发 → 编辑器收到空回车或截断文本。**必须分三步：先 `send_keys("^v")` → 等 500ms → 用 ValuePattern/vision 验证输入框有内容 → 再 `send_keys("{ENTER}")`。**

### 对话窗口读回复规则（v3.7）

从聊天应用用视觉读回复时容易读到自己的消息。**必须：**

1. send_keys({END}) 滚到底
2. 等 1s
3. 截图
4. vision：从底部往上找最近一条非我发送的消息
5. 如果读到自己的消息 → 重试

## 验证分层（v2.2+）

| 层 | 方法 | 耗时 | 适用 |
|---|------|------|------|
| 0 | UIA属性读回 | ~0ms | Win32/WPF/WinUI3控件 |
| 1 | 区域感知哈希(pHash) | ~1ms | 布局变化检测 + 变化幅度校验 |
| 2 | 本地OCR提取文字 | ~500ms | 需要读取具体文本 |
| 3 | 云端vision兜底 | 3-5s | 前三层都不可用 |

**假成功检测（v3.4）：** pHash 变了但变化幅度异常（全窗口灰掉→可能是弹窗遮挡）→ 判定失败。

**待落地—三元验证（Claude Sonnet 4.6 建议，2026-05-31）：** 当前 pass/fail 二元。加入 uncertain 状态 → 自动升级验证层（UIA→OCR→vision），不手动判断。详见 `references/claude-agent-architecture-feedback.md`。

**待落地—Anchor 心跳：** 每轮操作前确认关键控件仍存在。UIA FindFirst anchor elements → 不存在则触发恢复流程。成本低于"操作失败再 rollback"。

**待落地—外部 Watchdog：** 守护进程独立观测系统状态（窗口消失/应用崩溃/弹窗遮挡），发信号但不调工具。

## DPI 坐标校准

`logical_x = uia_x / (AppliedDPI / 96)`

## 重试规则

- 每步执行前 → `safepoint.checkpoint(action="click", description="...")`
- 同一操作失败 → `safepoint.rollback(reason)` → 回上一安全点，换恢复路径
- `can_recover()` 为 True → 按 `get_recovery_action()` 换路径重试，不原地撞墙
- `can_recover()` 为 False（连续3次rollback）→ 报 `DESKTOP_CONTROL_FAILED: [窗口] [操作] [原因]`
- UIA element操作失败 → 降级坐标点击再试1次
- 坐标也失败 → 降级视觉路径再试1次（受熔断器约束）
- 全部路径失败 → 报 `DESKTOP_CONTROL_FAILED`

## Win11 已知坑

| 应用 | 坑 | 绕路 |
|------|-----|------|
| 文件资源管理器 | 地址栏 ValuePattern.SetValue 超时（面包屑控件） | SetFocus + clipboard+^a^v+Enter |
| Edge | Get-Process MainWindowHandle=0 | UIA RootElement 按 ClassName 定位 |
| Edge (另法) | FindWindow('MSEdgeWinClass') 返回0 | Get-Process -Id PID → $proc.MainWindowHandle → ShowWindow(9)+SetForegroundWindow ✅（2026-05-28实测） |
| 网页聊天 | Enter键不发消息 | DeepSeek/ChatGPT网页：粘贴文本后必须**点击发送按钮**（圆形箭头图标），Enter只换行。先用vision找按钮坐标，再mouse_event点击 |
| Settings | SystemSettings MainWindowHandle=0 | UIA 只读 |
| iLink | 快速连续调用 → rate limited (ret=-2) | 失败后等 2 分钟 |

### Store 应用激活降级链（v3.7）

Store 版应用（Claude Desktop、Settings 等）的 Win32 ShowWindow/SetForegroundWindow 经常返回 False 且静默失败。**降级链：**

```
1. ShowWindow(5) + SetForegroundWindow
   → True? 完成
   → False? ↓
2. mouse_click(窗口标题栏中心坐标)  # 物理点击激活
   → 截图验证标题栏高亮? 完成
   → 仍未激活? ↓
3. UIA FindFirst(目标编辑框) → SetFocus()  # 直接聚焦输入控件
   → ValuePattern 验证可读写? 完成
   → 仍失败? ↓
4. 通知用户「请点击 Claude Desktop 窗口」
```

**关键：** 步骤2的标题栏坐标——取窗口 BoundingRectangle，标题栏 y 坐标 = rect.Top + 15px，x 坐标 = rect.Left + rect.Width/2。

## Qt应用铁律

- **SOM视觉 → 看**（读消息、确认状态、定位元素）
- **iLink协议 → 动**（发消息、推送通知）
- **不越界**：视觉不操控Qt窗口，协议不读UI状态
- **Win32 mouse_event/SendKeys 对Qt窗口不可靠，不用**
- 实测数据: `references/qt-win32-barrier.md`

### iLink 联系人限制

- **必须先建立会话**：目标联系人或群聊必须先给 bot 发过消息，才会出现在 `context-tokens` 中。`send_message(action='list')` 只列出已有令牌的联系人
- **特殊账号不可达**：文件传输助手等微信内置特殊账号无法通过 iLink 发送（尝试 `filehelper`/`file_helper`/`filehelper@im.wechat` 均返回 `ret=-3`），除非 bot 从该聊天窗口收到过消息
- **限流**：连续多次快速发送触发 `ret=-2 rate limited`。同一目标 3 次失败后应冷却 30s+
- **多进程坑**：`Get-Process -Name "Weixin"` 可能返回多个进程，`MainWindowHandle` 变成数组导致 Win32 API 调用失败。用 `window_list` 或 UIA 获取正确 hwnd
- 详测: `references/ilink-contact-discovery.md`

## 护盾速查

| 护盾 | 模块 | 一句话 |
|------|------|--------|
| 健康度 | `HealthMonitor` | score 0-100，连续失败降级，连续成功恢复 |
| 时间盾 | `TimeGuard` | 单操作30s/会话10min/缓存5min |
| 熔断器 | `CircuitBreaker` | 连续3次超时→阻断vision 60s |
| 环境检测 | `EnvDetector` | 分辨率/DPI变→清SOM缓存 |
| 安全点 | `SafePointManager` | 每步前记快照，失败回退不撞墙 |

详细降级/恢复决策表: `references/shields-v3.4-v3.5.md`

## 参考

- 接口架构: `references/architecture-v3.5.md`
- 五护盾详解: `references/shields-v3.4-v3.5.md`
- 视觉路径详解: `references/visual-path-v3.3.md`
- 接口协议: `scripts/interfaces.py`
- 五护盾实现: `scripts/robustness.py`
- SOM锚点引擎: `scripts/visual_som_anchor.py`
- SOM锚点引擎: `scripts/visual_som_anchor.py`
- UIA SOM 引擎: `~/.hermes/skills/uia-state-machine/scripts/uia_som.py`
- **CC 快刀（v3.7 新增）：** `scripts/som-scan`（截图→vision→缓存元素）、`scripts/som-click`（按编号点击）、`scripts/ps-run`（PowerShell UTF-8桥接器）
- **UIA 守护进程（v3.8）：** `scripts/uia_daemon.ps1` — 持久 FocusChanged handler，Chromium UIA 树不缩回骨架
- 完整参考: `references/desktop-control-reference.md`
- 多应用实战测试(v3.5): `references/v3.5-field-test-2026-05-23.md`
- **v3.5 实战测试**: `references/v3.5-field-test-2026-05-23.md`
- iLink 联系人限制: `references/ilink-contact-discovery.md`
- **GitHub:** https://github.com/jiangxiao642-spec/hermes-desktop-control
- **Claude Desktop 操控:** `references/claude-desktop-uia-prosemirror.md`
- Claude Desktop UIA + ProseMirror: `references/claude-desktop-uia-prosemirror.md`
- **安全审计:** `references/deepmind-agent-attack-traps.md`（DeepMind 六类 Agent 攻击陷阱，2026-04）
- **DirectShell UIA 四阶段激活:** `references/directshell-uia-activation.md`（Chromium/Electron 完整可访问性树暴露）
- **Claude 架构建议（三元验证/Anchor心跳/Watchdog）:** `references/claude-agent-architecture-feedback.md`（2026-05-31 通过 UIA 对话获取）
- **Claude Desktop EXE 版 UIA 实测:** `references/claude-desktop-exe-uia-results.md`（2026-05-31，126元素，输入框+消息可读写）
