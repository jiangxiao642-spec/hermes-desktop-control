# Phi-Ground-Any: GUI Grounding Model Analysis (2026-05-22)

> Microsoft 的 4B 参数 GUI 定位模型。与我们的 desktop-control 视觉路径直接相关。

## 基本信息

| 项 | 值 |
|---|---|
| 模型 | microsoft/Phi-Ground-Any |
| 参数 | 4B |
| 基座 | Phi-3.5-vision-instruct |
| 输入 | 文字描述 + 截图（固定 1680×1008） |
| 输出 | `<x>328</x><y>456</y>`（归一化到 10000 尺度） |
| 协议 | MIT |
| 发布 | 2026-05-07 |
| 热度 | 270 downloads / 15 likes（极早期） |
| HuggingFace | huggingface.co/microsoft/Phi-Ground-Any |
| GitHub | github.com/microsoft/Phi-Ground（34★） |
| 论文 | arxiv.org/abs/2507.23779（2025-07-31） |

## 精度数据

| 模型 | ScreenSpot-Pro | 备注 |
|---|---|---|
| GPT-5.4 | 85.4% | 当前最高 |
| GPT-5.2 | 86.3% | llm-stats数据 |
| Gemini 3 Pro | 72.7% | |
| Qwen3.6 Plus | 68.2% | 我们当前视觉后端 |
| 原版 Phi-Ground | 43.2% | 论文自报（端到端） |
| Phi-Ground-Any | **未上榜** | 微软未提交 |
| 基准最初最佳 | 18.9% | 论文基线 |
| ScreenSeekeR（级联搜索） | 48.1% | 无需额外训练 |

## ScreenSpot-Pro 基准

- 1581 条指令，23 款专业应用，5 个行业，3 个操作系统
- 真实高分辨率截图 + 专家标注
- 涵盖专业软件（非消费应用）
- 论文：arxiv.org/abs/2504.07981

## 与我们的相关性

**直接相关点：**
- 输入输出范式与 desktop-control 视觉路径完全一致：截图+描述→坐标
- 4B 参数意味着可本地部署（~8GB bf16），无需 API 调用
- MIT 开源，无许可障碍

**核心问题：**
- 精度不可靠：前身 Phi-Ground 在 ScreenSpot-Pro 上仅 43.2%
- 43% 意味着超过一半的定位是错的——对自动化来说不可接受
- 微软未提交 Phi-Ground-Any 到公开排行榜，精度透明性存疑

**可行路径（待验证）：**
1. **粗筛 + 精确认：** 本地 Phi-Ground 先粗定位候选区域 → 裁剪 200×200 → 云端 vision 模型精确确认
2. 好处：每个操作的云端 vision token 从全屏（~500px 截图）降到局部（200×200），成本降一个量级
3. 延迟：本地模型毫秒级，不影响整体速度

## 部署考量

- 模型约 8GB（bfloat16），需要 GPU 或足够内存的 CPU
- 可用 transformers 或 vllm 推理
- Windows 原生 Hermes（D:\hermes）可直接加载
- 输入必须 resize 到 1680×1008，坐标需反算回原始分辨率

## 决策状态（2026-05-22）

**暂不集成。** 理由：
- 发布仅两周，精度数据不透明
- 43% 的基准太低，不足以单独使用
- 等社区跑出更多实测数据再评估
- 优先级低于 B 站视频和闲鱼检测器

**记录原因：** 这个模型与我们的核心技术栈高度相关，未来 desktop-control 迭代时是第一候选集成的本地 grounding 模型。
