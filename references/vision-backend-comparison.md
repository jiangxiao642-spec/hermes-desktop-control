# Vision Backend 实测对比

> 2026-05-23。同一张截图+同一套prompt，两个模型对比。

## 像素坐标精度 (JSON coordinate prompt)

**qwen3.6-plus** (10轮，记事本安装按钮，200×200裁剪):
- 平均偏差：65px，最小50px，最大76px
- 命中率（按钮半径36px内）：0/10 = **0%**
- 系统性偏差：dx=+33, dy=+55（偏右下）
- 平均置信度：0.97（高confidence但全错）
- 结论：不会报像素坐标，不是随机差，是根本性不对齐屏幕坐标系

**qwen-vl-max** (10轮):
- 全部返回(100, 100) = 图片正中心
- 置信度全为0
- 手动验证：模型明确说"没有可见的按钮"
- 结论：找不到目标时诚实返回中心点+confidence=0，不是精度更好。

## 全屏SOM标注质量

**qwen3.6-plus**: 15-20s，通过Hermes vision_analyze管道，约3-18元素
**qwen-vl-max**: 2-3s（httpx直调），3元素（相当），更稳定

## JPEG压缩效果

全屏PNG(1707×1067, ~3.8MB) → JPEG质量60 → ~166KB
- Qwen3.6-plus: PNG超时→DeepSeek fallback崩溃；JPEG正常
- qwen-vl-max: 均正常
- JPEG对SOM标注精度无可见影响

## DeepSeek Vision

DeepSeek API (deepseek-chat/v4-pro) **不提供多模态视觉接口**。
开源模型 DeepSeek-VL2（OCR很强，OCRBench 834）需自己部署。
