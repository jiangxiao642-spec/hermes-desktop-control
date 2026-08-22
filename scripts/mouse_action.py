"""Windows鼠标操作脚本，通过 PowerShell 桥接执行。

Usage:
  python3 mouse_action.py click <x> <y>       # 左键点击
  python3 mouse_action.py right-click <x> <y>  # 右键点击
  python3 mouse_action.py double-click <x> <y> # 双击
  python3 mouse_action.py move <x> <y>         # 仅移动不点击

Output: a PowerShell command string for execution by the active host adapter.
"""

import sys

try:
    from click_script import click_script
except ImportError:
    from scripts.click_script import click_script

ACTIONS = ("click", "right-click", "double-click", "move")


def main():
    if len(sys.argv) < 2:
        print("Usage: mouse_action.py <action> [x] [y]", file=sys.stderr)
        print("Actions: click, right-click, double-click, move", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    if action not in ACTIONS:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 4:
        print("x and y required for this action", file=sys.stderr)
        sys.exit(1)

    try:
        print(click_script(action, sys.argv[2], sys.argv[3], ok_marker="ECHO OK").strip())
    except ValueError as exc:
        print(f"Invalid coordinate: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
