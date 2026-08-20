# nuphus-mcp OCR+YOLO 融合感知 —— 移植笔记 (2026-08-07)

来源: GitHub mrpulor-gh/nuphus-mcp (MIT, Rust)。浅克隆在 `D:\hermes\nuphus-mcp\`。
本文记录其 `desktop_perceive` 的 OCR+YOLO 融合逻辑, 以及如何移植进本 skill 的视觉 SOM 引擎。

## 为什么值得抄

本 skill 视觉路径目前 = vision_analyze + OCR (PaddleOCR)。短板: 纯图标按钮
(无文字) 无法被 OCR 发现, 视觉模型定位"那个圆形的发送按钮"成本高且不稳。
nuphus 的解法: PaddleOCR 看文字 + YOLO (OmniParser icon_detect) 看图标,
按 IoU 合并成统一 UiElement 列表, 自动推断元素类型。文字、图标一次全拿到。

## nuphus 的 perceive 流程 (desktop-api/src/vision/)

```
截图 (xcap) → 存盘 → perceive_image(path)
  ├── PaddleOCR (ONNX Runtime, 进程级共享引擎, ~80MB 模型)
  │     → OcrBlock[] {text, x, y, w, h}
  ├── YOLO icon_detect.onnx (可选, 缺失时降级 OCR-only, 诚实上报 yolo_available:false)
  │     → Element[] {kind:Icon, rect, confidence}
  └── merge(ocr_blocks, yolo_elements)
        → UiElement[] {id, kind, text?, rect, confidence, source}
```

关键参数:
- YOLO 输入 640x640 (Lanczos3 缩放), 输出契约 [1,3,640,640] → [1,5,8400]
  (cx, cy, w, h, conf 归一化坐标, 乘回原图 scale)
- YOLO_CONF_THRESHOLD = 0.25, NMS_IOU_THRESHOLD = 0.45
- 模型源: onnx-community OmniParser icon_detect 640x640 ONNX
  (hf-mirror.com 优先, huggingface.co 兜底; NUPHUS_MCP_YOLO_MODEL_URL 可覆盖)
- 模型目录: %APPDATA%\Nuphus\models (或 NUPHUS_MODELS_DIR)
- 模型完整性校验: 文件大小下限 + ONNX trial-load

## merge 算法 (可整体移植)

两轮:

Round 1 — OCR 块找 YOLO 框 (IoU > 0.3 取最优):
- 匹配成功 → UiElement {source: Both, kind: infer_kind(text, rect), rect: YOLO 框(更准), confidence: 两者平均}
- 无匹配 → UiElement {source: Ocr, kind: Text, rect: OCR 框}

Round 2 — 未匹配的 YOLO 框 → UiElement {source: Yolo, kind: Icon, text: None}

最后统一编号 id = 0..n。

## infer_kind 规则 (直接抄, 中文关键词已实测)

1. 宽高比 > 3 → Input (输入框特征)
2. 文本含关键词 → Input: "输入", "搜索", "请输入", "password", "email", "用户名", "密码"
3. 1-4 个字符且无标点 → Button
4. 其余 → Text

标点集合: ASCII 标点 + 。，、；：？！…（）《》“”‘’

## 与本 skill 的结合点

### 接口映射 (interfaces.py UIElement)

| nuphus UiElement | desktop-control UIElement |
|---|---|
| id | index |
| kind (Input/Button/Icon/Text) | element_type (大写首字母映射: Button/Edit/Icon/Text) |
| text | label (无 text 的 Icon 留空) |
| rect | bounds (x, y, w, h) |
| source (Both/Ocr/Yolo) | source = "vision-ocr-yolo" 或保持 "vision" + 加字段 |
| confidence | confidence (已有, 默认 0.85) |

新增可选字段: `yolo_available: bool` 上报 YOLO 是否可用 (诚实降级原则)。

### 接入路径 (两条, 推荐 A)

A. 作为新 SOMAnnotator 策略: 在 `scripts/interfaces.py` 注册 `register_strategy`
   新 annotator "ocr-yolo", 输出标准 UIElement 列表 → 现有 Pipeline 直接消费,
   无需改验证/护盾层。与 UIA 注释器并列, CrossValidator 自动交叉验证。

B. 增强现有 visual_som_anchor.py: 在其 FullSOM 阶段, OCR 之外并行跑 YOLO,
   merge 后统一编号。改动小但耦合现有缓存/pHash 逻辑。

### 依赖清单 (Windows)

- Python: `pip install onnxruntime pillow numpy` (已有 Pillow)
- ONNX 模型 (~80MB): icon_detect.onnx, 手动下载到
  `%APPDATA%\Nuphus\models\` 或 skill 自己的 models 目录
  (下载源: https://hf-mirror.com/onnx-community/OmniParser... 或
  nuphus 文档给的 gitee/hf-mirror 地址)
- PaddleOCR: 本 skill 已有经验 (references 及 MinerU 环境)

### 实施步骤 (按序)

1. 写 `scripts/ocr_yolo_annotator.py`:
   - 截图 → 存临时 PNG
   - PaddleOCR 跑文字块 (复用现有 OCR 能力)
   - onnxruntime 跑 icon_detect.onnx, 后处理: conf 过滤 0.25 → 坐标还原 →
     NMS (0.45) → Element[]
   - 移植 merge() 两轮合并 + infer_kind()
   - 输出 list[UIElement], source="vision-ocr-yolo"
2. interfaces.py 注册新 annotator (register_strategy)
3. Pipeline 里 annotator 优先级: UIA > ocr-yolo > 纯 vision
4. 验证: 拿一个纯图标界面 (如微信/工学云) 对比 OCR-only vs OCR+YOLO 的
   元素召回率; 确认 yolo 缺失时降级不报错

### 坑 (nuphus 已踩, 别重踩)

- 模型文件存在 ≠ 可用: 必须 ONNX trial-load 验证, 损坏文件要报
  yolo_available=false, 不假装可用
- YOLO 会话必须进程级共享: 每次调用重建会重载 80MB 模型
- 坐标: YOLO 输出是归一化, 必须乘回截图原始分辨率, 不是 640
- NMS 必做: 640 输入下同一图标可能出多个重叠框
- 截图尺寸越大推理越慢: 全屏 4K 下建议先缩放再送 YOLO, 或只对 ROI 跑

## 参考源码位置

- merge + infer_kind: `crates/desktop-api/src/vision/perceive.rs`
- YOLO 检测/NMS/预处理: `crates/desktop-api/src/vision/yolo.rs`
- 模型管理: `crates/desktop-api/src/vision/models.rs`
- OCR: `crates/desktop-api/src/vision/paddle_ocr.rs`
