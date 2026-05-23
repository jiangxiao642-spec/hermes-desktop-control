# 视觉后端切换：qwen3.6-plus → qwen-vl-max

> 2026-05-23 完成切换。

## 数据对比

| 指标 | qwen3.6-plus | qwen-vl-max |
|------|-------------|-------------|
| 全屏SOM延迟 | 15-20s | 2-3s |
| 稳定性 | httpx直调超时 | 稳定 |
| SOM质量 | 相当 | 相当 |
| 坐标精度 | 65px偏差(不可用) | 未独立测试 |
| 成本 | ~$0.01/次 | 略高(tokens多) |

## 切换方法

`~/.hermes/config.yaml` → `auxiliary.vision.model: qwen-vl-max` → 重启 Gateway。

零迁移成本（同一 dashscope API key）。

## JPEG 压缩要求

全屏 PNG(3.8MB) 发 Qwen 会超时。必须先用 .NET 转 JPEG 质量 60（~160KB）：

```powershell
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile("screenshot.png")
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | ? {$_.MimeType -eq "image/jpeg"}
$enc = New-Object System.Drawing.Imaging.EncoderParameters(1)
$enc.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, 60L)
$img.Save("output.jpg", $codec, $enc)
```

## 坐标精度结论

qwen3.6-plus 不能做 pixel grounding（10轮偏差 65px，命中率 0%）。
qwen-vl-max 在坐标测试中返回 confidence=0 并猜测中心点——也不能做。
自然语言描述 → DeepSeek 估算坐标仍是当前最优视觉路径。
待专门 GUI grounding 模型成熟后升级。
