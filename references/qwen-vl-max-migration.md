# Qwen Vision Backend Migration: qwen3.6-plus → qwen-vl-max

> 2026-05-23 切换。零代码改动，一行 config。

## 决策依据

| 指标 | qwen3.6-plus | qwen-vl-max |
|------|-------------|-------------|
| SOM全屏标注 | 15-20s | 2-3s |
| 稳定通过httpx+proxy | ❌ 频繁超时 | ✅ |
| SOM标注质量 | 相当 | 相当 |
| 像素坐标精度 | 65px偏差(不可用) | 未测试（不是主力场景） |
| 1024px大图 | 超时→Fallback崩溃 | 正常 |
| API key | 同一个 | 同一个 |
| 迁移成本 | — | 一行 config |

## 操作

```yaml
# ~/.hermes/config.yaml
auxiliary:
  vision:
    model: qwen-vl-max  # was: qwen3.6-plus
```

Gateway 重启后生效。

## 关键注意事项

1. **图像压缩仍然需要**：全屏PNG(3.8MB)→JPEG质量60(166KB)。即使qwen-vl-max更稳定，大图仍然增加延迟和token消耗。
2. **confidence=0 过滤**：qwen-vl-max 找不到目标时会返回confidence=0 + 自然语言。解析器必须过滤 confidence=0 的结果，防止将模型"猜的中心点"当有效数据。
3. **SOM标注prompt不变**：同一套FULLSOM_PROMPT在两模型上都可用，输出格式一致。
