# Computer Use — 模型原生视觉操控

Codex 的 computer use 核心是 **同一个模型既看图又决策** — 截图直接发给 GPT-5.5，模型输出结构化动作（坐标+按键），执行后再截图循环。

## 与我们现有管道的差异

| | 现有 desktop-control | Codex computer use |
|---|---|---|
| 截图 | PowerShell / bridge | Agent app 内置 |
| 视觉 | qwen-vl-max 先描述 → DeepSeek 再决策 | GPT-5.5 看图直接输出动作 |
| 执行 | UIA / mouse_event / SendKeys | 同样调 Win32 API |
| 循环 | 分开的 vision→reasoning→execute 步骤 | 一个 API 调用完成"看+想" |
| 优势 | UIA 可精确读控件 | 模型原生理解 UI，不丢信息 |
| 劣势 | 两阶段损失信息 | 需要多模态大模型 |

## 我们的实现：computer_use.py

独立 Python 脚本，不依赖 Hermes 运行时：
- PowerShell 截图（100px 网格叠加）
- qwen-vl-max 替代 GPT-5.5（免费，DashScope）
- 解析 JSON 动作 → PowerShell 执行
- 循环：截图→决策→执行→验证→截图

路径：`~/.hermes/scripts/computer_use.py`

## 限制

- qwen-vl-max 非专用 GUI grounding 模型，坐标精度弱于 GPT-5.5
- 网格标注帮助定位但仍有偏差
- 不推 GitHub（本地工具）
