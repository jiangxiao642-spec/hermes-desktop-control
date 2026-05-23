# GUI Agent 行业现状（2026年5月）

来源：zylos.ai 综述（2026-02-08）+ 后续新闻至 2026-05-23。

## 四家大厂产品

| 厂商 | 产品 | 技术路线 | 关键数据 |
|------|------|---------|---------|
| Anthropic | Computer Use API | 纯视觉（截图+VLM） | 首个生产级CU API（2024.10），tool version `computer_use_20251124` |
| OpenAI | Operator→ChatGPT Agent | CUA (GPT-4o+RL训练) | JS重型网站87%，WebArena 58%，OSWorld 38% |
| Google | Project Mariner | Gemini 2.0 | ScreenSpot 84%，WebVoyager 83.5%，同时10任务 |
| Microsoft | UFO²→UFO³ Galaxy | UIA+vision混合+多agent | Windows桌面自动化，UFO³扩展到多设备协同 |

## 技术路线共识：混合架构

2026年行业收敛到同一个结论：
- **DOM/accessibility tree 默认走**（快、省token、精确）
- **vision 兜底非标准UI**（Canvas、游戏、自定义渲染、Qt）
- **纯视觉**（Anthropic路线）：通用但贵（单截图15000+ tokens），2-5s/action
- **纯结构树**（Agent-E）：静态网站强（95.7%），动态弱（27.3%）

**对我们的意义：desktop-control v3.3 的 UIA优先+SOM视觉兜底 正好是行业共识路径。**

## 关键基准

| 基准 | 当前最优 | 人类 | 说明 |
|------|---------|------|------|
| OSWorld | ~38% (OpenAI) | 72.36% | 369个跨桌面任务 |
| WebArena | 71.2% | — | 浏览器导航+表单 |
| ScreenSpot | 84% (Google) | — | 多模态屏幕理解 |
| AndroidWorld | 100% (mobile-use) | — | 116个安卓任务 |
| WebVoyager | 89.1% (Browser-Use混合) | — | 真实网页任务 |

OSWorld 38% vs 人类 72% —— 桌面GUI agent 还有很大空间。跨应用多步骤是最难的。

## 关键挑战（与我们踩过的坑对应）

1. **可靠性**：click→verify→retry 事务机制是生产级必须的。VeriSafe Agent 引入逻辑验证替代概率验证。→ 我们 v3.3 的 think-act-verify 方向正确，但验证层目前只到 pHash，需要加强。
2. **速度**：VLM 推理 2-5s/action，Nova 系统通过 GPU 空间共享优化。→ 我们切 qwen-vl-max 后 SOM 从 15-20s 降到 2-3s，符合行业水平。
3. **长程规划**：多步骤任务错误累积，agents 往往不识别自己失败了。→ 手动 think-act-verify 模板 vs 行业在探索自动错误恢复。

## 开源标杆

- **Mobile-Agent-v3/GUI-Owl**：AndroidWorld 73.3%，OSWorld 37.7%
- **mobile-use 框架**：AndroidWorld 100%（首个满分）
- **DigiRL**：1.5B VLM + RL 训练，67.2%（比 GPT-4V 的 8.3% 高 49.5 个百分点）

## GPT-5.5 是最强 CU 模型（2026-05-23）

> "GPT-5.5 is the best model in the world for autonomous, multi-step computer use — and it is not particularly close."

4月23日发布，比 GPT-5.4 晚不到7周。GPT-5.5 Instant 5月5日成为 ChatGPT 默认。
