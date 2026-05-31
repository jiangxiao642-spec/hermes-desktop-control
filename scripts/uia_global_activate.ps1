# UIA Global Activation — 登录时运行一次
# 设 SPI_SETSCREENREADER + 注册 FocusChanged handler
# 此后所有 Chromium/Electron 应用自动构建完整可访问性树

Add-Type @"
using System; using System.Runtime.InteropServices;
public static class DS {
    [DllImport("user32.dll")] public static extern bool SystemParametersInfoW(uint a, uint b, IntPtr c, uint d);
}
"@

# 全局屏幕阅读器标志
[DS]::SystemParametersInfoW(0x0047, 1, [IntPtr]::Zero, 3) | Out-Null

# FocusChanged handler（全局，所有 Chromium 受益）
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$handler = [System.Windows.Automation.AutomationFocusChangedEventHandler]{ param($s,$e) }
[System.Windows.Automation.Automation]::AddAutomationFocusChangedEventHandler($handler)

Write-Host "UIA Global Activation: Screen reader ON, FocusChanged handler registered"
Write-Host "All Chromium/Electron apps will now expose full accessibility trees."

# Keep alive — this window stays open to keep handler from being GC'd
Write-Host "Keep this window open. Minimize, don't close."
while ($true) { Start-Sleep -Seconds 60 }
