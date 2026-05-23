# Qwen vision 返回给 DeepSeek 的格式

> 2026-05-23 调研。分析 Hermes vision_analyze 工具的管道。

## 管道结构

```
DeepSeek (主模型) 调用 vision_analyze(image_url, question)
  → _handle_vision_analyze() 格式化 prompt
  → dashscope/qwen3.6-plus (辅助视觉模型) 
  → 返回纯文本
  → DeepSeek 读取文本结果
```

## Qwen 返回格式

**纯自然语言文本。** 无 JSON schema、无结构化坐标、无强制格式。

`vision_tools.py:1044-1050` 中的 prompt 模板：

```
You are a precise visual analysis assistant. Focus only on what is asked.
Answer the following question about this image directly and concisely:

{question}

If the answer is not visible or unclear in the image, say so explicitly.
Do not describe unrelated elements.
```

Qwen 看到的就是这段 + 图片 + 你的 question，用自己的自然语言回答。格式完全取决于 question 怎么写。

## 对 desktop-control 的影响

- **UIA 路径**：不受影响。SOM 扫描走 PowerShell → JSON，不经过 vision
- **视觉路径**：靠 prompt 工程请求 Qwen 返回特定格式（如 `[N] Type "Name" (x,y,w,h)`），但 Qwen 可以忽略格式要求
- **坐标直出**：已验证不可行。Qwen 不会报像素坐标（偏差 65px/0%命中率）
- **自然语言描述**：当前最优。Qwen 描述"按钮在图片下方中央"→ DeepSeek 估算坐标

## 换模型的可能性

dashscope 上有专门的视觉模型如 `qwen-vl-max`、`qwen-vl-ocr`，但它们同样不是 GUI grounding 模型。专门的 grounding 模型（Phi-Ground-Any 等）是另一条产品线，需独立部署。
