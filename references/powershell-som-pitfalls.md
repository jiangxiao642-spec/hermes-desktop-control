# PowerShell-UIA Bridge: SOM Scan Pitfalls

Lessons from building the SOM (Set-of-Mark) PowerShell scanner for Windows UIA.

## P1: Variable scope in .ps1 files

When a PowerShell function is defined inside a `.ps1` script file, it runs in a
child scope. Variables defined at script level are READABLE but NOT WRITABLE
from within functions unless prefixed with `$script:`.

```powershell
# Script level
$elements = @()
$index = 0

function Scan-Element($el) {
    # WRONG — creates local $index, $elements
    $index++
    $elements += $elem

    # RIGHT — modifies script-level variables
    $script:index++
    $script:elements += $elem
}
```

This does NOT apply to inline `powershell -Command "..."` execution — only to
`powershell -File script.ps1`.

## P2: Hash table internals — no bare assignments

Inside a PowerShell `@{}` hash literal, every line is interpreted as a key-value
pair. A bare `$rect = $el.Current.BoundingRectangle` INSIDE the hash becomes a
non-string key → `ConvertTo-Json` fails with "Keys must be strings".

```powershell
# WRONG — $rect becomes a hash key
$elem = @{
    name = "foo"
    $rect = $el.Current.BoundingRectangle   # THIS IS A KEY, NOT AN ASSIGNMENT
    bounds = @($rect.X, $rect.Y)
}

# RIGHT — assign $rect BEFORE the hash
$rect = $el.Current.BoundingRectangle
$elem = @{
    name = "foo"
    bounds = @($rect.X, $rect.Y)
}
```

## P3: Win11 UIA ControlType degradation

Win11's new UI framework (Notepad, Settings, some UWP apps) reports ALL controls
as `ControlType.Pane` regardless of their actual type. The true type is in
`ClassName`:

| Element | ControlType | ClassName |
|---------|------------|-----------|
| Text edit area | ControlType.Pane | Edit |
| Button | ControlType.Pane | Button |
| Status bar | ControlType.Pane | msctls_statusbar32 |

Fix: resolve type by ControlType first, fall back to ClassName for "Pane":

```powershell
$interactive_ct = @("Button","Edit","ComboBox",...)
$interactive_cn = @("Edit","Button","ComboBox","ListBox","ScrollBar","msctls_statusbar32","Static")

$resolved_type = $ct
if ($ct -notin $interactive_ct) {
    if ($cn -in $interactive_cn) {
        if ($cn -eq "msctls_statusbar32") { $resolved_type = "StatusBar" }
        elseif ($cn -eq "Static") { $resolved_type = "Text" }
        else { $resolved_type = $cn }
    }
}
```

## P4: BOM encoding for Chinese characters

PowerShell 5.1 on Chinese Windows reads `.ps1` files as GBK (system ANSI) by
default. UTF-8 without BOM → garbled Chinese characters in strings → parser
errors. Fix: write `.ps1` files with UTF-8 BOM:

```python
with open(path, "w", encoding="utf-8-sig") as f:
    f.write(ps_script)
```

Pure ASCII scripts don't need BOM. But any script containing CJK characters
(like window title fallback strings) MUST have BOM.

## P5: catch {} silently eats everything

```powershell
try {
    # ... complex UIA operations ...
} catch {}
```

This swallows ALL errors — type resolution failures, hash construction errors,
method invocation failures. In debug mode, add error output:

```powershell
} catch { Write-Output "SCAN ERROR: $_" }
```

## Template: minimal working SOM scan

See `scripts/uia_som.py` → `generate_som_powershell_script()` for the full
production version. Key invariants:
- `$script:` prefix on all mutable script-level variables
- ClassName fallback for ControlType.Pane apps
- Hash keys must be string literals only
- BOM encoding when CJK strings present
