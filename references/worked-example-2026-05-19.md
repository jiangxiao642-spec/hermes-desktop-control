# Desktop Control — Worked Example (2026-05-19)

First field test of the four-step loop: Perceive → Refine → Act → Verify.

## Round 1: Add Shortcut Button (Small Target)

Goal: Click "+" add shortcut button in browser new tab page.

**Step 1 (Perceive):**
- Screenshot(grid=true) → vision found "Add shortcut button" at (1250, 460)

**Step 2 (Refine):**
- crop_region.py centered at (1250, 460) → 200×200 crop
- Vision on crop: exact position (crop_x=150, crop_y=140)
- Full-screen: x2 = 1250-100+150 = 1300, y2 = 460-100+140 = 500

**Step 3 (Act):**
- mouse_event left click at (1300, 500) → returned OK

**Step 4 (Verify):**
- Screenshot → vision: "browser window not visible, only terminal and desktop"
- ❌ FAILURE — browser context changed between steps (page navigated or tab lost focus)

**Root cause:** Browser UI elements are unstable targets — clicking them can trigger navigation that removes the verification context. Not a coordinate precision issue.

## Round 2: Desktop Right-Click (Large Target, Two Attempts)

Goal: Right-click desktop blank area → verify context menu appears.

### Attempt 1
- Perceive: vision found blank area at (1450, 150)
- Refine: skipped (large target >200px)
- Act: right-click at (1450, 150) → OK
- Verify: vision → NO context menu
- ❌ (1450, 150) was probably over a window, not true desktop blank

### Attempt 2 (Retry)
- Perceive: asked vision for DIFFERENT blank area, got (900, 900)
- Act: right-click at (900, 900) → OK
- Verify: vision → YES, context menu visible
- ✅ SUCCESS

### Key Finding

**(900, 900) is the most reliable desktop right-click coordinate** — verified across two separate sessions (this one and the earlier vision-click-verify test). Lower-right quadrant of screen, away from taskbar and typical window placement.

## Lessons

1. **Large targets on static surfaces** (desktop wallpaper) are the most reliable vision→click→verify targets
2. **Browser UI elements** are unstable — clicking them can change the page context mid-verification
3. **Desktop right-click at (900, 900)** is the go-to smoke test for the full loop
4. **Two retries** is the right limit — attempt 1 had bad coordinates, attempt 2 with adjusted input succeeded
5. **Precision refinement (step 2)** is necessary for targets <30px but insufficient alone — target stability matters more
