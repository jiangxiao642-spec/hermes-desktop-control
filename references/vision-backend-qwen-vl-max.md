# Vision Backend: qwen-vl-max

> 2026-05-23 切换。从 qwen3.6-plus → qwen-vl-max。理由：稳定性更好、速度 6-8x、精度相当、零迁移成本。

## 配置

```yaml
# ~/.hermes/config.yaml
auxiliary:
  vision:
    provider: dashscope
    model: qwen-vl-max          # was: qwen3.6-plus
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
```

同一 API key，同 endpoint，一行改完重启 Gateway 生效。

## 性能对比

| 指标 | qwen3.6-plus | qwen-vl-max |
|------|-------------|-------------|
| SOM全屏标注延迟 | 15-20s | 2-3s |
| 稳定性（Hermes管道） | 偶尔超时→fallback | 稳定通 |
| SOM标注质量 | 相当 | 相当 |
| 像素坐标精度 | 65px偏差/0%命中 | 不可用(confidence=0) |
| 大图超时风险 | 3.8MB PNG超时 | 166KB JPEG正常 |

## 关键限制

- **不能做 pixel grounding**。qwen-vl-max 和 qwen3.6-plus 都不会报像素坐标。
  10 轮坐标测试：qwen3.6-plus 偏差 65px(0%命中)，qwen-vl-max 返回 confidence=0。
  视觉路径坐标定位仍走自然语言描述→DeepSeek 估算路线。

- **大图需压缩**。全屏 PNG(1707×1067, 3.8MB)→Qwen超时→fallback到DeepSeek崩溃。
  解决方案：截图后立即转 JPEG 质量60（~166KB），SOM标注精度不受影响。

## JPEG 压缩脚本（PowerShell/Windows）

```powershell
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile("C:\Users\44829\hermes-screenshot.png")
$dest = "C:\Users\44829\hermes-temp\som.jpg"
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | 
    Where-Object { $_.MimeType -eq "image/jpeg" }
$encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
$encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
    [System.Drawing.Imaging.Encoder]::Quality, 60L)
$img.Save($dest, $codec, $encParams)
$img.Dispose()
```

## 回滚

如有问题，改回 `model: qwen3.6-plus`，重启 Gateway。
