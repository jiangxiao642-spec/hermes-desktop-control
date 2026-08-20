# Persistent UIA activation and adaptive accessibility-tree snapshots.

param(
    [int]$TargetPid,
    [IntPtr]$TargetHwnd,
    [int]$MinPollMilliseconds = 250,
    [int]$MaxPollMilliseconds = 2000,
    [int]$MaxElements = 5000
)

Add-Type @"
using System; using System.Runtime.InteropServices;
public static class DS {
    [DllImport("user32.dll")] public static extern bool SystemParametersInfoW(uint a, uint b, IntPtr c, uint d);
    [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumChildProc lp, IntPtr l);
    [DllImport("oleacc.dll")] public static extern uint AccessibleObjectFromWindow(IntPtr h, uint id, ref Guid riid, out IntPtr p);
    public delegate bool EnumChildProc(IntPtr h, IntPtr l);
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
    $name = "HWND-$hwnd"
} else {
    Write-Error "Need -TargetPid or -TargetHwnd"
    exit 1
}

if ($hwnd -eq [IntPtr]::Zero) {
    Write-Error "Target has no main window handle"
    exit 2
}

[DS]::SystemParametersInfoW(0x0047, 1, [IntPtr]::Zero, 3) | Out-Null
[DS]::SendMessageW($hwnd, 0x001A, 0x0047, [IntPtr]::Zero) | Out-Null
$focusHandler = [System.Windows.Automation.AutomationFocusChangedEventHandler]{ param($s,$e) }
[System.Windows.Automation.Automation]::AddAutomationFocusChangedEventHandler($focusHandler)

Start-Sleep -Milliseconds 250

$iid = [DS+IAccessible].GUID
$accessible = [IntPtr]::Zero
[DS]::AccessibleObjectFromWindow($hwnd, [DS]::OBJID_CLIENT, [ref]$iid, [ref]$accessible) | Out-Null
if ($accessible -ne [IntPtr]::Zero) {
    [Runtime.InteropServices.Marshal]::Release($accessible) | Out-Null
}
$probe = [DS+EnumChildProc]{ param($child,$unused)
    $candidate = [IntPtr]::Zero
    [DS]::AccessibleObjectFromWindow($child, [DS]::OBJID_CLIENT, [ref]$iid, [ref]$candidate) | Out-Null
    if ($candidate -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::Release($candidate) | Out-Null
    }
    [DS]::SendMessageW($child, [DS]::WM_GETOBJECT, [IntPtr]::Zero, [DS]::OBJID_CLIENT) | Out-Null
    return $true
}
[DS]::EnumChildWindows($hwnd, $probe, [IntPtr]::Zero) | Out-Null

function Get-SnapshotLines($root) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $pending = [System.Collections.Generic.Stack[object]]::new()
    $pending.Push($root)

    while ($pending.Count -gt 0 -and $lines.Count -lt $MaxElements) {
        $element = $pending.Pop()
        try {
            $elementName = ($element.Current.Name -replace "[`r`n|]", " ").Trim()
            $controlType = $element.Current.ControlType.ProgrammaticName -replace '^ControlType\.', ''
            $automationId = ($element.Current.AutomationId -replace "[`r`n|]", " ").Trim()
            $rect = $element.Current.BoundingRectangle
            $lines.Add("$controlType|$automationId|$elementName|$([int]$rect.X),$([int]$rect.Y),$([int]$rect.Width),$([int]$rect.Height)")

            $children = $element.FindAll(
                [System.Windows.Automation.TreeScope]::Children,
                [System.Windows.Automation.Condition]::TrueCondition
            )
            for ($i = $children.Count - 1; $i -ge 0; $i--) {
                $pending.Push($children.Item($i))
            }
        } catch {}
    }

    return $lines
}

$controlHome = if ($env:DESKTOP_CONTROL_HOME) {
    $env:DESKTOP_CONTROL_HOME
} elseif ($env:HERMES_HOME) {
    # Backward compatibility with existing Hermes installations.
    $env:HERMES_HOME
} else {
    "$env:USERPROFILE\.desktop-control"
}
$profileDir = Join-Path $controlHome "uia_profiles"
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
$snapFile = Join-Path $profileDir "$name.snap"

$pollMs = [Math]::Max(50, $MinPollMilliseconds)
$maxPollMs = [Math]::Max($pollMs, $MaxPollMilliseconds)
$previousBody = ""
$iteration = 0

Write-Host "[DAEMON] Target=$name hwnd=$hwnd"
Write-Host "[DAEMON] Snapshot=$snapFile poll=${pollMs}-${maxPollMs}ms"

try {
    while ($true) {
        $iteration++
        try {
            $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
            $snapshotLines = Get-SnapshotLines $root
            $body = $snapshotLines -join "`n"
            $snapshot = "# $name - UIA Snapshot #$iteration`n# Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff')`n# Total elements: $($snapshotLines.Count)`n---`n$body"
            [System.IO.File]::WriteAllText($snapFile, $snapshot, [System.Text.UTF8Encoding]::new($false))

            if ($body -ne $previousBody) {
                $pollMs = [Math]::Max(50, $MinPollMilliseconds)
                $previousBody = $body
                Write-Host "[$iteration] changed: $($snapshotLines.Count) elements"
            } else {
                $pollMs = [Math]::Min($maxPollMs, [int]($pollMs * 1.5))
            }
        } catch {
            Write-Warning "[$iteration] $($_.Exception.Message)"
            $pollMs = [Math]::Min($maxPollMs, [int]($pollMs * 1.5))
        }

        Start-Sleep -Milliseconds $pollMs
    }
} finally {
    [System.Windows.Automation.Automation]::RemoveAutomationFocusChangedEventHandler($focusHandler)
}
