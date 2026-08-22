"""Shared PowerShell click-script generator — single source of truth.

Used by both mouse_action.py and som-click so the injected PS1 stays
identical across entry points. Coordinates are validated as integers
before interpolation to keep untrusted input out of the PowerShell
string (PS injection guard).
"""

# user32.dll mouse_event flags
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010

# action -> [(down_flag, up_flag, sleep_ms_after_down), ...]
_CLICK_SEQUENCES = {
    "click": [(_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP, 80)],
    "right-click": [(_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP, 80)],
    "double-click": [
        (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP, 80),
        (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP, 200),
    ],
}

_HEADER = """Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
Start-Sleep -Milliseconds 80
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class M{{[DllImport("user32.dll")]
public static extern void mouse_event(int f,int dx,int dy,int d,int e);}}'"""


def click_script(action: str, x, y, ok_marker: str = "OK") -> str:
    """Build the PowerShell snippet performing action at (x, y).

    action:    click | right-click | double-click | move
    x, y:      integer screen coordinates (numeric strings like "100" are
               accepted and coerced)
    ok_marker: trailing line emitted on success; kept per-caller so
               existing bridge parsers keep working unchanged.
    """
    try:
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        raise ValueError(f"x/y must be integers, got x={x!r}, y={y!r}")

    if action == "move":
        events = ""
    elif action in _CLICK_SEQUENCES:
        lines = []
        for down, up, sleep_ms in _CLICK_SEQUENCES[action]:
            lines.append(
                f"[M]::mouse_event(0x{down:04X},0,0,0,0); "
                f"Start-Sleep -Milliseconds {sleep_ms}"
            )
            lines.append(f"[M]::mouse_event(0x{up:04X},0,0,0,0)")
        events = "\n".join(lines)
    else:
        raise ValueError(
            f"unknown action: {action!r} "
            "(expected click, right-click, double-click or move)"
        )

    script = _HEADER.format(x=x, y=y)
    if events:
        script += "\n" + events
    return script + "\n" + ok_marker


__all__ = ["click_script"]
