# Claude 架构反馈（2026-05-31 通过 UIA 直接对话获取）

## 来源
陈一通过 UIA 通道直接向 Claude Desktop（Sonnet 4.6）咨询桌面 agent 架构建议。

## 核心建议

### 1. 三元验证
当前验证是 pass/fail 二元。Claude 建议加入第三种状态 **uncertain**：
- pass → 继续
- fail → rollback + 重试
- **uncertain** → 自动升级验证层（UIA → OCR → vision），不需要手动判断

效果：避免"看起来成功了但不确定"的模糊状态被当作 pass 放行。

### 2. Anchor 心跳检测
每轮操作前对关键控件（输入框、发送按钮、窗口标题栏）做存活检测。
不是等到操作失败才发现窗口没了——成本比 rollback 低。

实现方向：UIA FindFirst 查 anchor elements → 存在→继续，不存在→恢复流程。

### 3. 外部 Watchdog
守护进程独立于操作脚本，不调用工具，只观察系统状态。
检测：窗口消失、应用崩溃、系统弹窗遮挡、网络超时。

与操作脚本的关系：watchdog 发信号，操作脚本决定是否中断/恢复。

### 4. UIA 事件驱动（替代轮询）
从每 2 秒轮询 dump 升级为事件驱动：
- 注册 StructureChanged / ValueChanged / InvokePattern.Invoked 事件
- 控件变化立刻得知，不等下一轮
- 配合 anchor 心跳：事件触发时验证关键 anchor 仍存在

### 5. 微信 CDP 探测（已验证为阴性）
微信 Windows 版 Qt 5.15 + WeChatAppEx 不监听任何 TCP 端口。
9220-9230 范围无 CDP 响应。消息区非 WebView 渲染。
结论：微信只走视觉路径，不投入 CDP 相关资源。

## 对话记录
完整对话见 Claude Desktop 会话历史（2026-05-31，陈一通过 UIA 发送）。
