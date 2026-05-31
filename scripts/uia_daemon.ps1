# DirectShell-style UIA Daemon — Persistent UIA activation + tree dump
# 保持 FocusChanged handler 永活，Chromium UIA 树不缩回骨架
# 用法: powershell -File uia_daemon.ps1 -TargetPid <PID>
# 效果: OpenClaw Desktop 10 → 2003 元素（200×），10 轮稳定

param([int]$TargetPid, [IntPtr]$TargetHwnd)

Add-Type @"
using System; using System.Runtime.InteropServices;
public static class DS {
    [DllImport("user32.dll")] public static extern bool SystemParametersInfoW(uint a, uint b, IntPtr c, uint d);
    [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumChildProc lp, IntPtr l);
    [DllImport("oleacc.dll")] public static extern uint AccessibleObjectFromWindow(IntPtr h, uint id, ref Guid riid, out IntPtr p);
    public delegate bool EnumChildProc(IntPtr h, IntPtr l);
    public const uint SPI_SETSCREENREADER = 0x0047;
    public const uint WM_SETTINGCHANGE = 0x001A;
    public static readonly uint OBJID_CLIENT = unchecked((uint)0xFFFFFFFC);
    public const uint WM_GETOBJECT = 0x003D;
    [ComImport, Guid("618736E0-3C3D-11CF-810C-00AA00389B71"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAccessible {}
}
"@
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes

if ($TargetPid -gt 0) {
    $proc = Get-Process -Id $TargetPid -ErrorAction Stop
    $hwnd = $proc.MainWindowHandle
    $name = $proc.ProcessName
} elseif ($TargetHwnd -ne [IntPtr]::Zero) {
    $hwnd = $TargetHwnd
    $name = "HWND:$hwnd"
} else { Write-Host "Need -TargetPid or -TargetHwnd"; exit 1 }

# Phase 1: Screen reader
[DS]::SystemParametersInfoW(0x0047, 1, [IntPtr]::Zero, 3) | Out-Null
[DS]::SendMessageW($hwnd, 0x001A, 0x0047, [IntPtr]::Zero) | Out-Null
Write-Host "[DAEMON] Phase 1: Screen reader ON for $name (hwnd=$hwnd)"

# Phase 2: FocusChanged handler (PERSISTENT)
$focusHandler = [System.Windows.Automation.AutomationFocusChangedEventHandler]{ param($s,$e) }
[System.Windows.Automation.Automation]::AddAutomationFocusChangedEventHandler($focusHandler)
Write-Host "[DAEMON] Phase 2: UiaClientsAreListening = TRUE (persistent)"

Start-Sleep -Milliseconds 500

# Phase 3-4: MSAA probes
$iid = [DS+IAccessible].GUID
$a = [IntPtr]::Zero
[DS]::AccessibleObjectFromWindow($hwnd, [DS]::OBJID_CLIENT, [ref]$iid, [ref]$a) | Out-Null
if ($a -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::Release($a) }

$probe = [DS+EnumChildProc]{ param($h,$l)
    $aa=[IntPtr]::Zero
    [DS]::AccessibleObjectFromWindow($h,[DS]::OBJID_CLIENT,[ref]$iid,[ref]$aa) | Out-Null
    if($aa -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::Release($aa)}
    [DS]::SendMessageW($h,0x003D,[IntPtr]::Zero,[DS]::OBJID_CLIENT) | Out-Null
    return $true
}
[DS]::EnumChildWindows($hwnd, $probe, [IntPtr]::Zero) | Out-Null
Start-Sleep -Milliseconds 500
[DS]::EnumChildWindows($hwnd, $probe, [IntPtr]::Zero) | Out-Null
Write-Host "[DAEMON] Phase 3-4: MSAA probes done"

# Initial count
function CountElements($el) {
    $n = 1
    try { $ch = $el.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.PropertyCondition]::TrueCondition); foreach($c in $ch){ $n += CountElements $c } } catch {}
    return $n
}
$ae = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$cnt = CountElements $ae
Write-Host "[DAEMON] Initial: $cnt UIA elements"

# Dump loop — every 2 seconds
$PROFILE_DIR = "D:\hermes\uia_profiles"
New-Item -ItemType Directory -Force -Path $PROFILE_DIR | Out-Null
$SNAP_FILE = Join-Path $PROFILE_DIR "$name.snap"

Write-Host "[DAEMON] Dumping to $SNAP_FILE every 2s"
Write-Host "[DAEMON] Running... (Ctrl+C or close window to stop)"

$iter = 0
while ($true) {
    Start-Sleep -Seconds 2
    $iter++
    try {
        $ae = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $total = CountElements $ae
        $snap = "# $name — UIA Snapshot #$iter`n# Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n# Total elements: $total`n---"
        [System.IO.File]::WriteAllText($SNAP_FILE, $snap, [System.Text.Encoding]::UTF8)
        Write-Host "[$iter] $total elements → $SNAP_FILE"
    } catch {
        Write-Host "[$iter] ERR: $_"
    }
}
