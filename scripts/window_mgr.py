"""Windows窗口管理脚本，通过 PowerShell 桥接执行。

Usage:
  python3 window_mgr.py activate <title_substring>   # 激活窗口
  python3 window_mgr.py minimize <title_substring>   # 最小化
  python3 window_mgr.py list                          # 列出所有可见窗口
  python3 window_mgr.py focus-by-class <class_name>   # 按类名激活

输出: PowerShell命令字符串。
"""

import sys

ACTIVATE = """
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class W{{
[DllImport("user32.dll")] static extern IntPtr FindWindow(string c,string t);
[DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int n);
public static bool Activate(string title){{
    IntPtr h=FindWindow(null,title);
    if(h==IntPtr.Zero){{var ws=System.Diagnostics.Process.GetProcesses();foreach(var p in ws){{try{{if(!string.IsNullOrEmpty(p.MainWindowTitle)&&p.MainWindowTitle.Contains(title)){{h=p.MainWindowHandle;break;}}}}catch{{}}}}}}
    if(h==IntPtr.Zero)return false;
    ShowWindow(h,9);return SetForegroundWindow(h);
}}
public static bool Minimize(string title){{
    IntPtr h=FindWindow(null,title);
    if(h==IntPtr.Zero){{var ws=System.Diagnostics.Process.GetProcesses();foreach(var p in ws){{try{{if(!string.IsNullOrEmpty(p.MainWindowTitle)&&p.MainWindowTitle.Contains(title)){{h=p.MainWindowHandle;break;}}}}catch{{}}}}}}
    if(h==IntPtr.Zero)return false;
    return ShowWindow(h,6);
}}
}}'
$ok=[W]::Activate("{title}")
if($ok){{ECHO ACTIVATED}}else{{ECHO NOT_FOUND}}
"""

MINIMIZE = """
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class W{{
[DllImport("user32.dll")] static extern IntPtr FindWindow(string c,string t);
[DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int n);
public static bool Minimize(string title){{
    IntPtr h=FindWindow(null,title);
    if(h==IntPtr.Zero){{var ws=System.Diagnostics.Process.GetProcesses();foreach(var p in ws){{try{{if(!string.IsNullOrEmpty(p.MainWindowTitle)&&p.MainWindowTitle.Contains(title)){{h=p.MainWindowHandle;break;}}}}catch{{}}}}}}
    if(h==IntPtr.Zero)return false;
    return ShowWindow(h,6);
}}
}}'
$ok=[W]::Minimize("{title}")
if($ok){{ECHO MINIMIZED}}else{{ECHO NOT_FOUND}}
"""

FOCUS_BY_CLASS = """
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class W{{
[DllImport("user32.dll")] static extern IntPtr FindWindow(string c,string t);
[DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int n);
public static bool Focus(string cls){{
    IntPtr h=FindWindow(cls,null);
    if(h==IntPtr.Zero)return false;
    ShowWindow(h,9);return SetForegroundWindow(h);
}}
}}'
$ok=[W]::Focus("{class_name}")
if($ok){{ECHO FOCUSED}}else{{ECHO NOT_FOUND}}
"""

LIST_WINDOWS = """
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class WL{{
[DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] static extern int GetWindowText(IntPtr h,StringBuilder t,int n);
public static string GetActiveTitle(){{
    IntPtr h=GetForegroundWindow();var sb=new System.Text.StringBuilder(256);
    GetWindowText(h,sb,256);return sb.ToString();
}}
}}'
Get-Process | Where-Object {{$_.MainWindowTitle -ne ''}} | Select-Object -First 20 Id,ProcessName,MainWindowTitle | Format-Table -AutoSize
Write-Output ("FOREGROUND: " + [WL]::GetActiveTitle())
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: window_mgr.py <action> [arg]", file=sys.stderr)
        print("Actions: activate, minimize, focus-by-class, list", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    if action == "list":
        print(LIST_WINDOWS.strip())
    elif action == "activate":
        title = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not title:
            print("Title substring required", file=sys.stderr)
            sys.exit(1)
        print(ACTIVATE.format(title=title).strip())
    elif action == "minimize":
        title = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not title:
            print("Title substring required", file=sys.stderr)
            sys.exit(1)
        print(MINIMIZE.format(title=title).strip())
    elif action == "focus-by-class":
        cls = sys.argv[2] if len(sys.argv) > 2 else ""
        if not cls:
            print("Class name required", file=sys.stderr)
            sys.exit(1)
        print(FOCUS_BY_CLASS.format(class_name=cls).strip())
    else:
        print(f"Unknown: {action}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
