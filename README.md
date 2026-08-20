# Desktop Control v3.11.1

Runtime-neutral Windows desktop automation for Codex, Claude Code, OpenClaw,
Hermes, and other agent hosts.

## Architecture

```text
Agent host adapter
  -> DesktopControlEngine
  -> anchor preflight and per-window lock
  -> UIA/SOM element discovery
  -> semantic or visual action
  -> adaptive verification
  -> executable recovery callback
  -> final evidence-backed result
```

The core engine does not depend on a specific agent product. Each host supplies
adapters for the capabilities it has: UIA, screenshots, pointer and keyboard,
clipboard, OCR, vision, process control, and permissions.

## Key Files

```text
SKILL.md                    Runtime-neutral operating policy
scripts/engine.py           Unified execution and recovery chain
scripts/waiting.py          Adaptive verification polling
scripts/interfaces.py       Shared domain types and protocols
scripts/robustness.py       Health, timeout, breaker, environment, recovery state
scripts/verify_dispatch.py  Anchor state and verification escalation
scripts/visual_som_anchor.py
                            Visual SOM parsing and cross-validation
scripts/uia_daemon.ps1      Persistent adaptive UIA tree snapshots
tests/                      Regression tests
references/                 Application-specific research and field notes
```

## Portability Contract

- Host-specific command names belong in adapters.
- Core operation and safety policy remains host-independent.
- Missing capabilities must fail explicitly.
- Non-idempotent actions are never repeated after execution merely because
  verification is uncertain.
- Completion requires observable UI evidence.

## Compatibility

Set `DESKTOP_CONTROL_HOME` to choose the runtime data directory. Existing Hermes
installations remain compatible through the legacy `HERMES_HOME` fallback.

## License

MIT
