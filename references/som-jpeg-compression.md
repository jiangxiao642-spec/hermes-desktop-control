# 全屏SOM标注 — JPEG压缩要求与模型对比

> 实验时间：2026-05-23

## 问题

全屏PNG截图（1707×1067，3.8MB base64）发送给 Qwen 时超时→Fallback到DeepSeek→DeepSeek 不支持 image_url→400 错误。

## 解决方案

截图后立即转 JPEG 质量60，体积从 3.8MB 降到 ~166-198KB。

**转换命令（Windows PowerShell）：**
```powershell
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile("screenshot.png")
$dest = "screenshot.jpg"
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
$encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
$encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, 60L)
$img.Save($dest, $codec, $encParams)
```

## 精度影响

实测：JPEG质量60的全屏SOM标注精度与PNG无差异（18元素正确识别，包括微信搜索框、AI对话标签、凌霄管理群）。

## 模型对比（SOM场景）

| 模型 | 速度 | Token | 质量 | 备注 |
|------|------|-------|------|------|
| qwen3.6-plus | 15-20s | ~500 | 基准 | 通用模型顺带做视觉 |
| qwen-vl-max | 2-3s | ~1550 | 相当 | 专业视觉模型，速度快6x |

## 推荐

全屏SOM标注使用 **qwen-vl-max**（速度优势明显，质量不差）。精准裁剪区域的语义识别可继续用 qwen3.6-plus（已有管道）。

## 集成位置

`desktop-control` skill v3.3 视觉路径 → `scripts/visual_som_anchor.py` → `VisualSOMCache` 类
