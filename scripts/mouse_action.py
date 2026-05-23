"""Windows鼠标操作脚本，通过 PowerShell 桥接执行。

Usage:
  python3 mouse_action.py click <x> <y>       # 左键点击
  python3 mouse_action.py right-click <x> <y>  # 右键点击
  python3 mouse_action.py double-click <x> <y> # 双击
  python3 mouse_action.py move <x> <y>         # 仅移动不点击

输出: PowerShell命令字符串，通过 mcp_windows_bridge_run_powershell 执行。
"""

import sys

CLICK_LEFT = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
Start-Sleep -Milliseconds 80
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class M{{[DllImport("user32.dll")]
public static extern void mouse_event(int f,int dx,int dy,int d,int e);}}'
[M]::mouse_event(0x0002,0,0,0,0); Start-Sleep -Milliseconds 80
[M]::mouse_event(0x0004,0,0,0,0)
ECHO OK
"""

CLICK_RIGHT = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
Start-Sleep -Milliseconds 80
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class M{{[DllImport("user32.dll")]
public static extern void mouse_event(int f,int dx,int dy,int d,int e);}}'
[M]::mouse_event(0x0008,0,0,0,0); Start-Sleep -Milliseconds 80
[M]::mouse_event(0x0010,0,0,0,0)
ECHO OK
"""

CLICK_DOUBLE = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
Start-Sleep -Milliseconds 80
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class M{{[DllImport("user32.dll")]
public static extern void mouse_event(int f,int dx,int dy,int d,int e);}}'
[M]::mouse_event(0x0002,0,0,0,0); Start-Sleep -Milliseconds 80
[M]::mouse_event(0x0004,0,0,0,0); Start-Sleep -Milliseconds 200
[M]::mouse_event(0x0002,0,0,0,0); Start-Sleep -Milliseconds 80
[M]::mouse_event(0x0004,0,0,0,0)
ECHO OK
"""

MOVE_ONLY = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
ECHO OK
"""

ACTIONS = {
    "click": CLICK_LEFT,
    "right-click": CLICK_RIGHT,
    "double-click": CLICK_DOUBLE,
    "move": MOVE_ONLY,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: mouse_action.py <action> [x] [y]", file=sys.stderr)
        print("Actions: click, right-click, double-click, move", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    if action not in ACTIONS:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)

    if action != "help":
        if len(sys.argv) < 4:
            print("x and y required for this action", file=sys.stderr)
            sys.exit(1)
        x, y = sys.argv[2], sys.argv[3]
        print(ACTIONS[action].format(x=x, y=y).strip())
    else:
        for name in ACTIONS:
            print(f"  {name}")


if __name__ == "__main__":
    main()
