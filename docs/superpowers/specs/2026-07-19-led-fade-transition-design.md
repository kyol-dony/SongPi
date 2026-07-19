# LED Fade Transition — Design

Date: 2026-07-19
Scope: `v1.2/Arduino/SongPiLedStrip/src/main.cpp` only. Python host code unchanged.

## Problem

When album recognition changes, the WS2812B strip snaps instantly to the new
color. The change should be a soft ~1 second fade.

## Decision

Fade runs in firmware, not on the host. The Arduino interpolates locally at
~60 fps, so the transition is smooth and the serial protocol stays one
`COLOR r g b` command per track change. Host-side fading was rejected: it
streams dozens of serial commands per transition and steps coarsely.

## Design

State in `main.cpp`:

- `CRGB fadeStart` — displayed color when the fade began
- `CRGB fadeTarget` — color being faded toward
- `unsigned long fadeStartMillis` — `millis()` at fade start
- `bool fadeActive` — false once the target is reached (stops needless `show()`)
- `FADE_MS = 1000` constant

Behavior:

- `COLOR r g b`: snapshot the currently displayed color into `fadeStart`, set
  `fadeTarget`, stamp `fadeStartMillis`, set `fadeActive`. No immediate fill.
- `loop()`: non-blocking. Every ~16 ms while `fadeActive`, compute
  `t = (millis() - fadeStartMillis) / FADE_MS`, clamp to 0–1, fill the strip
  with `blend(fadeStart, fadeTarget, t * 255)` (FastLED per-channel lerp),
  `show()`. When `t >= 1`, snap to `fadeTarget` and clear `fadeActive`.
- New `COLOR` arriving mid-fade restarts the fade from the currently displayed
  color — no visible jump.
- `OFF` fades to black through the same path.
- `BRIGHTNESS` remains instant (setup-time only, rare).
- Serial parsing is unchanged and never blocked by fade math.

## Error handling

No new failure modes: fade math is pure arithmetic on local state. Malformed
commands are ignored exactly as before.

## Testing / verification

- `pio run` must compile clean for the `uno` environment.
- Existing Python test suite must still pass (no host changes expected).
- Manual: play two tracks with contrasting covers; strip should blend over
  ~1 s instead of snapping.
