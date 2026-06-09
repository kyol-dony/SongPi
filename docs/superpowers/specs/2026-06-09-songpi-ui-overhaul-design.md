# SongPi UI Overhaul — Design Spec

**Date:** 2026-06-09
**Status:** Approved (pending user review of this file)
**Scope:** Visual + interaction overhaul of the Tkinter front-end in `v1.2/Files/shazam.py`. Builds on Tier 1 work (vignette, accent extraction, status pill, progress bar, active-lyric tint) already in the codebase.

## 1. Vision

SongPi is a **cinematic ambient lyric display**. The cover art drives mood; everything else is supporting cast. The screen feels alive — slow Ken Burns drift on the blurred backdrop, a breathing status dot, a quiet progress bar, a soft glow on the active lyric line — but never busy. The active lyric is the protagonist: tinted with a color sampled from the art, gently breathing, larger than its neighbors.

The same visual language scales from a 7" Raspberry Pi panel, to a laptop window, to a 55" fullscreen TV. No mode-specific UIs; one design, three contexts.

## 2. Decisions Captured From Brainstorming

| Question | Decision |
|----------|----------|
| Design philosophy | **Cinematic Ambient** (cover-art-driven mood, vignette scrim, lyrics as film subtitles) |
| Primary deployment | **All three contexts equally** — Pi panel, desktop window, fullscreen — scale by window size |
| Motion intensity | **Moderate** — Ken Burns backdrop, line slide+fade on advance, glow breath on active lyric, pulsing status dot |
| Visible items | Track title + artist, **album name**, **recent songs strip (with title + artist labels)**, status pill, progress bar, **cover-art reflection glow** |
| Wide-screen layout | **Split (editorial)** — cover + meta anchor left, lyrics flow right-aligned |
| Type voice | **Modern Display** — Space Grotesk (titles + active lyric) + Inter (body) |
| Lyric lines visible | **3 lines** — prev + now + next |
| Accent color source | **Per-song from cover art** |
| Idle state | **Ambient splash w/ animated gradient** + SongPi wordmark |

## 3. Visual Tokens

### Color

Foreground is locked to a dark-mode palette because the vignette overlay guarantees a dark scrim under all cover art (no brightness-toggle hack needed).

| Token | Value | Use |
|-------|-------|-----|
| `text/primary` | `#ffffff` | Title, metadata main, idle wordmark |
| `text/secondary` | `#cdd2da` | Artist, album |
| `text/tertiary` | `#8b919c` | Labels, idle status text |
| `text/lyric-prev` | `#6b7280` (~38% white) | Just-sung lyric line |
| `text/lyric-next` | `#a9b0bd` (~62% white) | Upcoming lyric line |
| `text/lyric-active` | `mix(accent, #ffffff, 0.35)` | Currently-singing lyric — guaranteed AA contrast |
| `surface/pill` | `#16181d` | Status pill background |
| `surface/track` | `#2a2d35` | Progress bar track |
| `surface/idle-base` | `#0a0a0c` | Canvas fallback before any art loads |
| `accent` | extracted | Lyric-active tint, status dot pulse, progress bar fill, cover halo |

**Accent extraction.** PIL quantize cover art (median-cut, 8 colors). For each swatch, score = `(saturation × 0.7 + value × 0.3) × count^0.3`, rejecting near-black (max RGB < 40) and near-white (min RGB > 220). Brighten if luminance < 160. Recomputed once per song-change. Already implemented in Tier 1 — no change required.

### Typography

Two-family system, fallback chain resolved once at startup via `tkFont.families()`.

| Role | Family chain | Weight | Use |
|------|--------------|--------|-----|
| `display` | Space Grotesk → Inter → system sans | 700 | Title, active lyric line, wordmark |
| `body` | Inter → system sans | 400/500 | Artist, album, prev/next lyric, history labels |
| `label` | Inter | 600 + 0.08em tracking + uppercase | Status pill, "RECENT" header |

**Responsive scale** (driven by window short-edge `s = min(w, h)`):

| Role | Formula |
|------|---------|
| Title | clamp(18, s × 0.035, 38) |
| Artist | clamp(11, s × 0.018, 18) |
| Album | clamp(10, s × 0.015, 15) italic |
| Lyric-active | clamp(22, s × 0.052, 64) |
| Lyric-context | clamp(13, s × 0.025, 24) |
| Status pill | clamp(9, s × 0.013, 14) |
| History title | clamp(9, s × 0.013, 13) |
| History artist | clamp(8, s × 0.011, 11) |

### Spacing

4 / 8 / 12 / 16 / 24 / 32 / 48 scale.
- `outer_margin` = clamp(20, min(w, h) × 0.04, 48)
- `panel_gap` = clamp(16, w × 0.04, 64)

### Radii

| Element | Radius |
|---------|--------|
| Cover art | 8 |
| Pill / chips | full (height / 2) |
| History thumbnails | 6 |
| Cards (future) | 14 |

## 4. Layout System

Breakpoints derived from window width `w` and aspect ratio `w / h`:

- **wide** — w ≥ 900 AND aspect ≥ 1.2 → Split layout
- **tall** — w < 900 OR aspect < 0.95 → Stacked layout
- **mid** — between → Compact split

### Split layout (wide)

```
┌─────────────────────────────────────────────────────────────┐
│ ● LISTENING                              recent songs ▸     │
│                                                             │
│   ┌────────┐   Midnight                meet me at midnight  │
│   │  ART   │   TAYLOR SWIFT       staring at the ceiling    │
│   │ (halo) │   Midnights         flashback to my mistakes   │
│   └────────┘                                                │
│                                                             │
│ ▬▬▬▬▬▬▬▬▬▬▬▬▬░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└─────────────────────────────────────────────────────────────┘
```

- Cover anchored lower-left, width = 22% of short-edge.
- Meta block immediately right of cover: title → artist (uppercase tracked) → album (italic).
- Lyrics column right-aligned, vertically centered, max-width 52% of window.
- Status pill top-left, 24px from edges.
- Recent strip top-right, horizontal, up to 4 thumbnails with stacked title + artist labels.
- Progress bar full-width at bottom, 16px from edges, 3px thick.

### Stacked layout (tall / small)

- Cover centered top, ~50% width.
- Meta centered below cover.
- Lyric column centered (3 lines stacked).
- History strip horizontal at bottom (above progress bar).
- Status pill stays top-left.

### Compact split (mid)

- Cover shrinks to 28% short-edge.
- Lyric column stays right-aligned.
- History strip drops to bottom under progress bar.
- Album line drops if vertical space tight.

**Mode-switch rule:** when window crosses a breakpoint, full redraw triggered by existing `trigger_full_redraw` debounce.

## 5. Motion System

Tkinter has no native easing; we interpolate manually via `after()` ticks.

### Tokens

| Token | Value | Use |
|-------|-------|-----|
| `dur/micro` | 180ms | Line color/opacity change |
| `dur/short` | 320ms | Line slide-fade-in on advance |
| `dur/medium` | 600ms | Splash crossfade, layout reflow |
| `dur/idle-pulse` | 1600ms | Breathing dot cycle |
| `dur/ken-burns` | 24s | Backdrop drift cycle |
| `easing/out` | cubic-ease-out (4 samples) | All entries |

### Primitives

1. **Ken Burns backdrop.** Pre-render two PIL frames per song-change (1.04× toward NW, 1.10× toward SE). Tk crossfades between them via `canvas.coords()` and stipple-based alpha simulation. Cycle 24s ease-in-out. Disabled when `motion.ken_burns_enabled = false` or auto-detected low-power.

2. **Active-lyric advance transition.** When lyric index changes:
   - New line enters: y-offset +8px → 0, color 40% → 100% accent over 320ms.
   - Old "now" demotes to "prev" position, color → 38% white over 180ms.
   - "next" demotes to "now", color 62% white → accent-tinted active.

3. **Active-lyric breathing glow.** Stacked larger transparent-color text behind the main line, sin-curve color blend toward accent over 3.6s period, ±15% amplitude. Simplified on Pi 3: no halo render, color sin-pulse only.

4. **Status dot pulse.** Tier 1 — sin curve, period 1.6s, mixing accent ↔ 55% dim-toward-pill-bg. Goes flat grey on idle/no-match/error.

5. **Progress bar.** Existing real-time anchor calculation, accent fill width updated each `refresh_lyrics_display` tick (~250ms). Add a 2px under-stroke at 30% opacity for soft glow.

6. **Cover-art reflection halo.** One-time PIL pre-render per song: Gaussian-blurred accent disc, 1.18× cover size, 35% alpha. Static — no per-frame work.

7. **Splash idle gradient.** Full-window mesh-gradient using 3 accent stops cycling warm/cool/neutral, drifting via the same Ken Burns scheme. Wordmark centered.

### Frame budget

Steady-state cost on Pi 4 (1080p fullscreen): ~80ms aggregate across 60+ ticks per second = ~1.5% CPU. Track-change spike: ~250ms one-time. Idle splash cycle: ~40ms PIL per 12s.

### Reduced motion

New config flag `gui.motion_reduced`. When true (or auto-detected Pi 3 / armv7):
- No Ken Burns
- No glow breath
- No idle gradient drift
- Line transitions snap (instant)
- Pulse dot becomes static accent dot

## 6. Components

### 6.1 Status pill (existing, refine)

- Rounded rect, height 28–40px (clamps), padding 10×20px.
- Dot (8–14px) + uppercase tracked label.
- Anchored top-left 24px from edges.

States: `listening`, `recognizing` (faster pulse), `no-match` (3s, flat dot), `error` (red dot), `idle` (flat dot), `starting` (cold-boot).

### 6.2 Cover art card

- Square, 8px radius.
- Accent halo behind, 32px Gaussian blur, 35% alpha, sized 1.18× cover.
- LANCZOS resample, full-bleed.

### 6.3 Meta block

- Title (display 700, primary white).
- Artist (label 600 uppercase tracked, secondary).
- Album (body 400 italic, tertiary).
- **Remove** the existing `♩ ◎ ◌` glyph prefixes — they read as noise.

### 6.4 Lyric column

- Three lines: prev / now / next.
- Active tinted with `mix(accent, white, 0.35)`, display weight, 1.4–1.6× context line size.
- Crossfade transition (see Motion §5.2).
- Right-aligned in split, center-aligned in stacked.

### 6.5 Recent songs strip

- Horizontal in split layout (top-right, max 4 items).
- Horizontal-bottom in stacked / compact-split.
- Each item: 28–40px rounded thumb (radius 6) + 2-line label (title body 500, artist body 400 tertiary).
- Items dim from newest (left, 100%) to oldest (right, 50% opacity).
- Item gap: 12px.
- Reserve ≥44×44 hit target per item for future tap-to-surface; no behavior yet.

### 6.6 Progress bar

- 3px height, 16–24px from window edges.
- Track `#2a2d35`, fill accent + 2px under-stroke at 30% accent alpha for glow.
- Updated each `refresh_lyrics_display` tick from sync anchor.

### 6.7 Idle splash

- Triggered when no recent song AND no active recognition match for >10s.
- Full-window mesh-gradient (3 accent stops cycling warm/cool/neutral, Ken Burns drift).
- "SongPi" wordmark centered, display 700 + 0.05em tracking, primary white at 60% opacity.
- Status pill remains top-left.
- 600ms dissolve when a track is recognized.

### 6.8 Wordmark

- "SongPi" rendered display 700 + 0.05em tracking.
- Optional small mark: lowercase dot beside the "P" tinted accent.
- Used in idle splash; future: about/loading.

## 7. States & Edge Cases

| State | Trigger | Visual |
|-------|---------|--------|
| `cold-boot` | App start, no `last_state` | Idle splash, pill = "STARTING…" pulsing |
| `idle-listening` | No match >10s OR first cycle | Idle splash, pill = "LISTENING…" pulsing |
| `idle-restored` | `last_state` loaded, no current match | Last song's cover + meta dimmed to 55%, pill = "LISTENING…", lyrics hidden, progress inert |
| `recognizing` | Recording or shazamio call in flight | Current visual, pill = "RECOGNIZING…" with faster pulse |
| `playing-with-lyrics` | Match + lyrics resolved | Full track UI |
| `playing-no-lyrics` | Match but LRCLIB+NetEase miss | Track UI without lyric column; tertiary label "no synced lyrics for this track" in its place |
| `no-match` | Recognition returned no match | Persist last `idle-restored` UI; pill = "NO MATCH" for 3s, then "LISTENING…" |
| `offline-error` | Network or audio device failure | Pill = "OFFLINE" red dot, last UI dimmed further, retry on next cycle |
| `shutdown` | WM close | 300ms fade to black |

### Track-change choreography

When a new recognition resolves to a *different* track:

1. 0–200ms — incoming cover + halo crossfade in over the outgoing.
2. 100–300ms — meta block fades out, new meta fades in (100ms behind cover).
3. 0–300ms — accent color animates from old → new on lyric-active tint, status dot, progress bar fill.
4. After: lyric column reseeds at the active line from the sync anchor.

Same-track re-recognition (anchor refinement): no visual change.

### Idle entry/exit

- Entering: backdrop crossfades to mesh-gradient over 600ms; meta/lyric/progress fade out; wordmark fades in last.
- Exiting: reverse — wordmark fades out first, then mesh dissolves into the new track's blurred art.

### Error visibility

Errors never block the UI. The status pill carries the signal; the main stage retains the last good visual.

### Font fallback

If neither Space Grotesk nor Inter is installed, fall back through the chain in `get_ui_font_family()`. Layout must remain legible with system sans only.

### Reduced motion

When `gui.motion_reduced = true` OR auto-detected low-power: all motion primitives in §5 collapse to static / snap. Status dot becomes flat accent.

## 8. Implementation Scope

### Files touched (v1.2)

- **`v1.2/Files/shazam.py`** (primary). Refactor visual code into named functions:
  - `render_meta_block(layout_info)` — title/artist/album rendering with new type voice.
  - `render_lyric_column(layout_info)` — replaces parts of current `render_lyrics_labels`; adds transition state.
  - `render_recent_strip(layout_info)` — extends current cinematic history with title/artist labels.
  - `render_idle_splash(layout_info)` — new.
  - `render_cover_halo(layout_info)` — new; PIL halo composite around cover.
  - `apply_track_change_choreography(old, new)` — new; runs the 300ms crossfade dance.
  - `tick_lyric_transition()` — new; per-frame lyric advance interpolator.
  - `tick_ken_burns()` — new; backdrop crossfade driver.
  - Existing Tier 1 helpers remain (`render_status_pill`, `render_progress_bar`, `extract_accent_color`, `apply_vignette`, `get_ui_font_family`, `draw_rounded_rect`).

- **`v1.2/Files/config.json`** — new knobs:
  - `gui.ken_burns_enabled: true`
  - `gui.motion_reduced: false`
  - `gui.idle_splash_enabled: true`
  - `gui.accent_halo_intensity: 0.35`
  - `lyrics.lines_visible: 3`

- **(Optional)** `v1.2/Files/fonts/` — bundle Inter + Space Grotesk TTFs. Register at startup via `tkextrafont` if installed, else rely on OS-installed fonts. Fallback chain handles absence.

### Out of scope

- Audio-reactive bars (no live spectrum signal between recognitions).
- Touch/click handlers on history thumbnails (reserve hit targets only).
- Light-mode variant (cinematic ambient = dark-only by design).
- Settings UI (config stays JSON).
- Live Pi 3 profiling (best-effort fallback profile, no perf SLA).

### Risks

- **Ken Burns on Tk** is unusual. If implementation proves expensive or jittery, fall back to static blurred bg with only the per-song reflection halo for visual interest.
- **Custom font bundling on Pi** may require `tkextrafont` or system pre-install. Decide at implementation time; fallback chain already handles missing fonts gracefully.
- **Glow halo without native blur** — Tk has no GPU compositing. We simulate with stacked larger transparent-color text. May read as "fat" rather than glowy. Tune in implementation; cut if it looks bad.

## 9. Acceptance

- Visual language consistent across split / stacked / compact-split breakpoints.
- Active lyric line clearly emphasized; eye locks on it within 100ms of attention.
- Accent color demonstrably tracks cover art (different colors for distinctly-colored albums).
- Track-change choreography reads as deliberate, not jarring (≤ 500ms total).
- Idle splash never feels like a "broken / no signal" screen.
- On Pi 4 (1080p), steady-state CPU < 4% with motion enabled.
- On Pi 3, reduced-motion profile keeps the UI responsive (resize, fullscreen toggle remain under 200ms).
- All existing functionality (Shazam recognition, LRCLIB/NetEase lyrics, history, last_state) survives the refactor unchanged.

---

**Next:** Once you approve this file, I'll invoke the `writing-plans` skill to produce an executable implementation plan.
