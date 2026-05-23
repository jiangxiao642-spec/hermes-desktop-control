# 视觉后端切换：qwen3.6-plus → qwen-vl-max

> 2026-05-23 决策。一行配置变更，零迁移成本。

## 切换原因

| 指标 | qwen3.6-plus | qwen-vl-max |
|------|-------------|-------------|
| 全屏SOM延迟 | 15-20s | 2-3s |
| 稳定性 | 大图(3.8MB)超时+fallback到DeepSeek崩溃 | 166KB JPEG稳定通 |
| 坐标精度 | 10轮偏差65px，0%命中 | 不适用（不用它做坐标） |
| SOM质量 | 相当 | 相当 |
| 微信全屏SOM | 未测 | 19元素，坐标合理 |

## 切换操作

```yaml
# ~/.hermes/config.yaml
auxiliary:
  vision:
    provider: dashscope
    model: qwen-vl-max  # 原: qwen3.6-plus
```

改后重启 Gateway：`hermes gateway restart`

## 关键数据

- 全屏JPEG压缩：质量60，3.8MB→166KB
- 全屏SOM延迟：2-3s（Hermes管道调用）
- 微信窗口19元素标注通过
- 同一个 dashscope API key，零额外费用

## 已知限制

- 不适合做像素坐标定位（confidence=0时返回默认中心点）
- 自然语言描述准确，JSON坐标格式不可靠
- SOM标注（结构化列表格式）是其最佳用途
