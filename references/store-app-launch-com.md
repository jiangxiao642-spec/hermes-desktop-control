# Store 应用启动：COM Shell.Application（2026-05-25 实测）

## 问题

Claude Desktop（Store版）的 Win32 激活全链失败：
- ShowWindow(5) → False
- SetForegroundWindow → False  
- Start-Process "claude" → 找不到文件
- Start-Process "shell:AppsFolder\..." → 找不到文件

## 有效方案

```powershell
$am = New-Object -ComObject Shell.Application
$am.NameSpace("shell:AppsFolder").Items() | 
    Where-Object {$_.Name -like "*Claude*"} | 
    ForEach-Object { $_.InvokeVerb("open") }
```

成功启动 Claude Desktop（hwnd 出现，进程 claude 运行）。

## 限制

- 启动后窗口可能不可见（GetWindowRect 返回全零）
- 仍需用户配合激活或使用 UIA SetFocus
- Win32 ShowWindow/SetForegroundWindow 即使进程在跑也返回 False
