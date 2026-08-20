---
name: desktop-control
description: "Runtime-neutral Windows desktop GUI control for Codex, Claude Code, OpenClaw, Hermes, and other agent hosts. Uses UI Automation first with visual fallback."
version: 3.11.1
author: Chen Yi + CC (Claude Code)
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [desktop-automation, uia, gui, windows, som, vision]
    related_skills: [computer-use]
---

# Desktop Control Skill v3.11.1

## Scope

Use this skill to control Windows desktop applications.

- Primary path: Microsoft UI Automation (UIA).
- Fallback path: screenshots, Set-of-Marks (SOM), OCR, and vision.
- Supported targets: Electron, Win32, WPF, WinUI 3, and visually accessible Qt applications.
- Out of scope: application business logic and task-specific workflow design.

This skill defines how to operate a desktop application. The calling task defines what the operation is meant to accomplish.

## Runtime Portability

This skill is agent-host neutral. Its core logic must work with Codex, Claude
Code, OpenClaw, Hermes, and other runtimes that can provide equivalent desktop
capabilities. Host-specific tool names must remain in adapters, never in the
control engine or operation policy.

A runtime adapter may provide:

- UIA tree capture and semantic element actions;
- screenshots and region capture;
- keyboard, pointer, clipboard, and window management;
- OCR and vision inference;
- process lifecycle and permission handling.

Missing capabilities must be reported explicitly. The engine must not silently
assume that a Hermes MCP command, Codex computer-use tool, Claude integration,
or OpenClaw bridge exists.

## Core Rule: UIA First

Prefer semantic UIA operations whenever they are available:

1. Use `InvokePattern` for buttons and commands.
2. Use `ValuePattern` or `SetValue` for compatible fields.
3. Read state and content from the UIA element tree.
4. Use element bounds only when no semantic interaction pattern exists.
5. Use OCR or vision only when UIA cannot expose the required control or state.

Known UIA blind spots include:

- Qt applications with minimal accessibility trees.
- Store/MSIX applications whose AppContainer blocks external UIA access.
- Custom web controls such as some `el-select` dropdowns.
- Canvas, WebGL, and image-only controls.

## Electron and Chromium Activation

Before scanning an Electron or Chromium application, activate persistent UIA
listening through the current host adapter. For example, a Windows bridge may expose:

```text
mcp_windows_bridge_uia_activate(pid=<target-pid>)
```

Alternatively, start `scripts/uia_daemon.ps1` and keep it alive. Chromium may collapse its accessibility tree after the listener exits.

Store/MSIX builds may remain inaccessible even after activation. Use the visual fallback in that case.

## Operation Pipeline

All state-changing GUI operations must enter through `DesktopControlEngine`.
Do not manually assemble anchor checks, retries, or recovery around individual
scripts. The engine owns the per-window lock and the complete operation chain.

For every GUI task, the engine follows this sequence:

1. Classify the target application and choose UIA, protocol, keyboard, or visual control.
2. Check health, circuit-breaker state, window identity, resolution, DPI, and focus.
3. Verify that key anchor controls still exist.
4. Build an element map from UIA or visual SOM.
5. Cross-check UIA and visual results when both are available.
6. Create a checkpoint before any state-changing action.
7. Execute one action.
8. Verify the expected result.
9. Retry through a different route when verification is uncertain or fails.
10. Report `DESKTOP_CONTROL_FAILED` with the target, action, and reason when recovery is exhausted.

The engine never repeats a non-idempotent action after the operator ran but
verification remained uncertain. This prevents duplicate messages, submissions,
and confirmations.

## Adaptive Waiting

Use `AdaptiveWaiter` for post-action verification. It polls immediately, starts
with a short delay, backs off while the UI is stable, and resets to fast polling
when observed state changes. It also learns a moving average per operation type.

Fixed sleeps are allowed only for low-level input timing such as mouse button
down/up separation. Application readiness and operation completion must be
determined from observable state, not a hard-coded delay.

## Ternary Verification

Verification results are:

- `PASS`: the expected state is confirmed.
- `FAIL`: evidence contradicts the expected state.
- `UNCERTAIN`: available evidence is insufficient.

Never convert `UNCERTAIN` to success. Escalate verification automatically:

```text
UIA property -> region pHash -> local OCR -> vision
```

The implementation lives in `scripts/verify_dispatch.py`. Shared result types are defined in `scripts/interfaces.py`.

## Anchor Heartbeat

Before each action, confirm that stable controls such as the composer, send button, title, or navigation region still exist. A sharp reduction in UIA element count can indicate a collapsed accessibility tree or a changed window.

When anchors disappear:

1. Restore and foreground the target window.
2. Reactivate persistent UIA listening if applicable.
3. Rescan the element tree.
4. Switch to the visual path if UIA remains incomplete.

## Element Selection Priority

Use the following priority:

1. UIA element with a stable `AutomationId` and a supported interaction pattern.
2. UIA element identified by role, name, hierarchy, and bounds.
3. Keyboard command with a verifiable result.
4. Visual SOM element with current screenshot bounds.
5. Raw coordinates only as a final, freshly verified fallback.

Never reuse stale coordinates after a window move, resize, DPI change, scroll, or layout update.

## Action Interface

Preferred logical operations:

```text
click element=7
type element=3 text="hello"
read element=5
```

Expected implementations:

- `click`: UIA invoke first, then verified bounds click, then visual fallback.
- `type`: focus the field, paste through the clipboard, verify the value, then submit separately.
- `read`: UIA value or text first, then OCR or vision for the element region.

## Text Input

For multilingual or long text, prefer clipboard paste over simulated typing.

Use this sequence:

1. Focus the target field.
2. Write the text to the clipboard.
3. Send `Ctrl+V`.
4. Wait at least 500 ms for long content.
5. Verify that the field contains the expected text.
6. Send `Enter` or invoke the submit control as a separate action.

Do not combine paste and submit into one `send_keys` call. Do not rely on `SetValue` for React-controlled fields unless the application is known to synchronize it correctly.

## Verification by Action Type

### Click

Expected evidence may include:

- the button state changes;
- a menu or dialog appears;
- the clicked control disappears;
- a new element or view becomes available.

Verify with UIA first, then OCR, pHash, or vision. Retry once through a different control route.

### Type

Verify the input field value through UIA or OCR. If it does not match, select all and replace the content once before failing.

### Open Application

Verify that a window with the expected class, process, title, or anchor controls exists. Process creation alone is not sufficient evidence.

### Navigate

Verify the resulting page title, URL, selected navigation item, or stable view anchor.

### Scroll

Rescan after scrolling and verify that new content is visible. Existing SOM indexes are invalid after the viewport changes.

## Application Routing

| Target | Preferred route | Notes |
|---|---|---|
| Notepad and standard Win32/WPF apps | UIA | Stable controls and automation IDs are usually available. |
| File Explorer | UIA | Use keyboard paste for the address bar when `ValuePattern` is unreliable. |
| Office applications | UIA | Use the application's native accessibility tree. |
| VS Code and accessible Electron apps | UIA | Keep the UIA listener alive to expose the full Chromium tree. |
| Claude Desktop EXE build | UIA | Content may only be exposed after login. |
| Store/MSIX applications | Visual fallback | AppContainer can block external UIA access. |
| Windows Settings | UIA when accessible, otherwise visual | Window handles and external UIA can be inconsistent. |
| Edge or Chrome shell | Keyboard first | Prefer `Ctrl+L`, `Tab`, and `Enter`; use Playwright for web-page DOM operations. |
| Qt applications such as WeChat | Visual read, protocol action | UIA may expose only a skeleton tree. |
| Canvas or image-only interfaces | SOM/OCR/vision | Verify every coordinate-based action. |

## Web Content Boundary

Use Playwright or a browser-specific automation plugin for DOM-level web operations whenever possible. Use this desktop skill for:

- browser window management;
- native file pickers and permission dialogs;
- browser chrome, tabs, and address bars;
- pages that cannot be reached through the browser automation channel.

Do not use UIA coordinate clicking as the default way to operate ordinary web elements.

## Qt Rule

For Qt applications with an unusable UIA tree:

- use SOM, OCR, or vision to read visible state;
- use a supported protocol such as iLink for state-changing actions when available;
- verify protocol actions by observing the final GUI state;
- do not assume that a successful API response proves the visible operation completed;
- avoid repeated blind `mouse_event` or `SendKeys` retries.

## Safety and Recovery

Before a state-changing action, record:

- target window identity;
- current screenshot or perceptual hash;
- action description;
- expected result;
- recovery route.

Recovery rules:

1. Retry a failed UIA action once through verified element bounds.
2. If bounds control fails, rescan and retry once through the visual route.
3. Do not repeat an identical failed action without obtaining new state.
4. Stop after the configured recovery limit.
5. Report the exact failed target and evidence.

A checkpoint does not guarantee that external application changes can be undone. It records enough state to choose a safer recovery route.

## Circuit Breaker and Health

The supporting modules provide:

- `HealthMonitor`: tracks success and failure trends.
- `TimeGuard`: limits action and session duration.
- `CircuitBreaker`: blocks a repeatedly failing route.
- `EnvDetector`: invalidates cached coordinates after environment changes.
- `SafePointManager`: records pre-action state for recovery decisions.

Do not bypass an open circuit breaker by repeating the same low-confidence action through a renamed command.

## DPI Calibration

When converting physical UIA coordinates to logical coordinates:

```text
logical_x = uia_x / (AppliedDPI / 96)
logical_y = uia_y / (AppliedDPI / 96)
```

Recalculate after moving a window between monitors.

## Conversation Applications

When reading the latest response from a chat application:

1. Scroll to the bottom.
2. Wait for the view to settle.
3. Capture a fresh screenshot or UIA snapshot.
4. Locate the most recent message that was not sent by the user.
5. Verify its role and position before returning its contents.

When submitting a message, verify that the new message appears in the conversation. A click, keypress, or API return value alone is not proof of delivery.

## Known Windows Issues

- `MainWindowHandle` may be zero for Edge and some WinUI applications. Locate the window through the UIA root and its class name.
- `SetForegroundWindow` may fail silently for Store applications. Try verified title-bar activation or focus a known child control.
- Some Element UI `el-select` components expose read-only text without an invoke or expand pattern. Use a fresh visual target for the dropdown arrow and verify the resulting list.
- Long clipboard pastes need a delay before submission.
- Browser chat pages may treat Enter as a newline. Invoke or visually click the send button and verify the posted message.

## Required Completion Evidence

Never claim success based only on an attempted action. A completed GUI operation must have at least one observable result:

- changed UIA property;
- expected element appeared or disappeared;
- OCR readback matched;
- target window or view changed;
- screenshot evidence confirmed the final state.

## Implementation Files

- `scripts/interfaces.py`: shared interfaces and result types.
- `scripts/engine.py`: unified engine, per-window locking, anchor preflight, and recovery execution.
- `scripts/waiting.py`: adaptive verification polling and latency history.
- `scripts/robustness.py`: health, time, breaker, environment, and safe-point logic.
- `scripts/verify_dispatch.py`: verification escalation and anchor checks.
- `scripts/visual_som_anchor.py`: visual SOM anchors.
- `scripts/uia_daemon.ps1`: persistent UIA listener with adaptive, named-element tree snapshots.
- `scripts/som-scan`: screenshot and element annotation command.
- `scripts/som-click`: indexed element click command.
- `scripts/ps-run`: UTF-8 PowerShell bridge.

## References

Load reference documents only when the target or failure mode requires them. Important starting points:

- `references/architecture-v3.5.md`
- `references/shields-v3.4-v3.5.md`
- `references/visual-path-v3.3.md`
- `references/directshell-uia-activation.md`
- `references/el-select-web-component-uia.md`
- `references/web-form-automation-pattern.md`
- `references/qt-win32-barrier.md`
- `references/claude-desktop-uia-prosemirror.md`
- `references/computer-use-approach.md`

Repository: `https://github.com/jiangxiao642-spec/hermes-desktop-control`
