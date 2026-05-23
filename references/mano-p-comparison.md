# Mano-P 与 desktop-control 对比分析

> 分析时间：2026-05-22。基于 Mano-P 公开资料（arxiv 2509.17336、dev.to 架构文章、GitHub README）。

## Mano-P 概述

- **项目：** Mininglamp-AI/Mano-P（明略科技开源），MIT 协议
- **定位：** 开源 GUI-VLA agent，Apple Silicon 边缘设备本地运行
- **方案：** 纯视觉——不看 DOM、不看 UIA、不看平台 API，只看屏幕像素 → 决定操作
- **模型：** 自研 72B（云端，OSWorld #1 58.2%）+ 4B 量化版（Mac M4 4.3GB，476 tok/s prefill）
- **训练：** Mano-Action 框架——三阶段（SFT → 离线RL → 在线RL），双向 Text↔Action 一致性优化
- **优化：** GSPruning（Global Spatial Pruning）——保留 anchor points + 识别 semantic outliers，2-3× 加速
- **数据：** 60,000 GUI 轨迹、300万+ 操作动作，覆盖主流桌面和 Web 工作流
- **13 个 benchmark SOTA**：OSWorld #1 (58.2%)、WebRetriever NavEval 41.7（超 Gemini 2.5 Pro 的 40.9 和 Claude 4.5 的 31.3）、ScreenSpot-V2、MMBench 等

## 架构对比

| 维度 | Mano-P | desktop-control v3.1 |
|------|--------|---------------------|
| 感知方式 | 纯视觉（只看像素） | UIA 优先 + 视觉兜底 |
| 平台 | macOS（Apple Silicon） | Windows |
| 操作方式 | 视觉坐标 | element(UIA)优先 → 坐标 fallback |
| 模型 | 自研 GUI-VLA（4B-72B） | 通用 LLM + UIA routing |
| 部署 | 本地（边设备） | 云端 + WSL 桥接 |
| OSWorld 精度 | 58.2%（#1 specialized） | 未跑 benchmark |
| 隐私 | 本地运行，数据不出机 | 云端推理 |
| 输入优化 | GSPruning（模型内部 token 剪枝） | 输入侧裁剪（crop_region，全屏→目标区域） |
| 验证闭环 | think-act-verify（训练机制） | 四层验证(Tier 0-3) + think-act-verify 操作模板 |
| Headless | 无专门方案（依赖 macOS 屏幕录制权限） | 虚拟显示器方案调研中 |

## 关键洞察

### 纯视觉的天花板
OSWorld 58.2% 不是"视觉不够好"的问题，是"光看像素能读懂多少"的硬限制。
看不到 AutomationId、控件名、DOM 结构——很多"这按钮到底能不能点"的判断只能靠猜测。
我们 UIA 优先策略在理论上精度应该更高——能直接读到控件身份、状态、可用 Patterns。

### 平台差异不可忽视
Mano-P 在 macOS 上跑得稳，因为苹果 Accessibility API 覆盖统一、有系统屏幕录制权限。
Windows 碎片化严重（Win32/WPF/WinUI3/Electron/Qt 各有 UIA 特征），单一视觉方案会撞更多墙。
我们的分层 fallback 策略是 Windows 生态的必要复杂度，不是过度工程。

### GSPruning 的核心思路
1. **Anchor Points**：在截图中保留关键空间结构锚点（如窗口边界、菜单栏位置）
2. **Semantic Outliers**：识别对比度/颜色/形状异常的 UI 元素（按钮、输入框通常跟背景对比度高）
3. **25% token 保留** → 成功率仅降 6%，速度翻 2-3 倍

我们不做模型训练，但降维成"输入侧裁剪"效果相同——先截全屏拿坐标，再用目标 bounds 裁 200×200 区域发给 vision。3-5s → <1s。

### think-act-verify 循环
Mano-P 把它做进了训练：模型生成操作时同步生成"预期结果描述"，RL 阶段用预期 vs 实际做奖励信号。
我们做成操作模板——每条视觉路径操作带"预期/验证/失败"三要素，失败时不是"重试"而是"降级到X或报FAILED含原因"。

## 已落地借鉴（v3.1）

| 借鉴点 | Mano-P 做法 | 我们做法 | 文件 |
|--------|-----------|---------|------|
| 输入侧裁剪 | GSPruning token 剪枝 | crop_region 区域截图 | desktop-control SKILL.md "视觉路径"段 |
| think-act-verify | 训练内化 | 操作指令模板 | desktop-control SKILL.md "操作指令格式"段 |

## 不可借鉴的部分

- **专用 VLA 模型训练**：我们依赖通用 LLM（DeepSeek/GPT），不走自研模型路线
- **Mac 独占**：跟我们 Windows 路线不冲突，但 macOS 的单一 API 环境让纯视觉方案比 Windows 上更有可行性
- **纯视觉放弃结构化信息**：与我们 UIA 优先策略矛盾。他们能做到 58.2% 已经很惊人了，但我们在 Windows 上走 UIA 优先可以超过这个数字

## Headless 问题

Mano-P 没有专门的 headless 方案——macOS 屏幕录制权限足以在显示器关闭时继续截图。
Windows 无此机制，需要虚拟显示器或 HDMI 假负载。这是我们独有的工程问题，他们不用操心。

## 性能基线参考

- 4B 量化模型在 Apple M4 Pro (64GB) 上：476 tok/s prefill, 76 tok/s decode, 4.3GB 峰值
- 未来如果在 Windows 边设备上做本地视觉定位，这是可以参照的性能数据
