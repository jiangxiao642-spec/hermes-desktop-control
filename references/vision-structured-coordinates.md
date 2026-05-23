# 坐标直出模式：JSON 提取层

## 流程（陈一执行）

```
1. screenshot → 全屏截图
2. crop_region.py → 裁 200×200 目标区域
3. vision_analyze(裁剪图, prompt用vision-json-coordinate-prompt.md模板) → qwen 返回文本
4. JSON 提取 → 解析 (x, y, confidence)
5. 判断：
   - x == -1 or confidence < 0.5 → 回退旧模式（全屏截图 + vision 自然语言描述）
   - 否则 → screen_x = crop_left + x, screen_y = crop_top + y → mouse_action click
6. 验证闭环
```

## 提取层代码

```python
import re
import json

def extract_coordinates(vision_response: str) -> dict | None:
    """
    从 vision 返回文本中提取 JSON 坐标。
    返回 {"x": int, "y": int, "confidence": float} 或 None。
    """
    if not vision_response:
        return None
    
    # 匹配第一个 JSON 对象
    match = re.search(r'\{[^{}]*"x"\s*:\s*-?\d+[^{}]*\}', vision_response, re.DOTALL)
    if not match:
        # 宽松匹配：任意花括号对
        match = re.search(r'\{.*?\}', vision_response, re.DOTALL)
    
    if not match:
        return None
    
    try:
        data = json.loads(match.group())
        x = data.get("x")
        y = data.get("y")
        confidence = data.get("confidence", 0)
        
        if x is None or y is None:
            return None
        
        return {"x": int(x), "y": int(y), "confidence": float(confidence)}
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def resolve_coordinates(vision_response: str, crop_left: int, crop_top: int) -> dict:
    """
    从 vision 返回中解析坐标并转换为屏幕绝对坐标。
    兜底 prompt 应保证所有返回都有 JSON，但保留 None 分支防意外。
    """
    result = extract_coordinates(vision_response)
    
    if result is None:
        return {"mode": "fallback", "reason": "parse_failed"}
    
    if result["x"] == -1 or result["confidence"] < 0.5:
        return {"mode": "fallback", "reason": "not_found_or_low_confidence"}
    
    return {
        "mode": "json",
        "screen_x": crop_left + result["x"],
        "screen_y": crop_top + result["y"],
        "confidence": result["confidence"]
    }
```

## 与旧模式的分流

| 条件 | 走什么 |
|------|--------|
| x != -1 且 confidence >= 0.5 | 坐标直出 → mouse_action click |
| x == -1 或 confidence < 0.5 | 回退全屏截图 + vision 自然语言描述 |
| parse 失败（兜底 prompt 生效后不应出现） | 同上回退 |

## 兜底 prompt 行

```
找不到目标时返回：{"x": -1, "y": -1, "confidence": 0}
```

这行关键——它让 qwen 在找不到目标时也返回 JSON 而非自然语言，
消除了提取层的双分支。confidence < 0.5 的判断是额外的安全网。
