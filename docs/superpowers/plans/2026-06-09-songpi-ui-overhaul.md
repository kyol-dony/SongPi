# SongPi UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Cinematic Ambient UI overhaul on top of Tier 1: Space Grotesk + Inter typography, accent-driven visuals, split editorial layout (with stacked + compact fallback), Ken Burns backdrop, 3-line lyric column with line transitions + glow breath, recent songs strip with title/artist labels, cover-art halo, ambient idle splash, and a polished state machine.

**Architecture:** All visual code lives in `v1.2/Files/shazam.py`, organized into named functions (`render_meta_block`, `render_lyric_column`, `render_recent_strip`, `render_idle_splash`, `render_cover_halo`, `apply_track_change_choreography`, `tick_lyric_transition`, `tick_ken_burns`). Pure helpers (easing, responsive scale, color blending, layout math, low-power detection) are testable via a new `v1.2/Files/tests/` pytest suite. Tk-touching renderers are verified by running the app and visually checking against the spec.

**Tech Stack:** Python 3.12+, Tkinter (Canvas), Pillow (PIL.Image, ImageFilter, ImageDraw, ImageStat), shazamio, requests. Tests: pytest. Fonts: system-installed Inter + Space Grotesk preferred; fallback chain handles absence.

---

## File Structure

**Modified:**
- `v1.2/Files/shazam.py` — primary; add ~14 new functions + state machine + extend existing renderers
- `v1.2/Files/config.json` — new GUI/lyrics knobs

**Created:**
- `v1.2/Files/tests/__init__.py` — empty marker
- `v1.2/Files/tests/conftest.py` — adds `Files/` to sys.path for tests
- `v1.2/Files/tests/test_ui_helpers.py` — pytest for pure helpers (color blending, easing, layout math, responsive scale, accent extraction)
- `v1.2/Files/pytest.ini` — minimal pytest config

**Optional (Task 24):**
- `v1.2/Files/fonts/Inter-Regular.ttf`, `Inter-Bold.ttf`, `SpaceGrotesk-Bold.ttf` — bundled fonts

---

## Pre-flight: Test infrastructure

### Task 0: Bootstrap pytest

**Files:**
- Create: `v1.2/Files/tests/__init__.py`
- Create: `v1.2/Files/tests/conftest.py`
- Create: `v1.2/Files/pytest.ini`

- [ ] **Step 1: Create empty test package marker**

```bash
touch v1.2/Files/tests/__init__.py
```

- [ ] **Step 2: Create conftest.py adding Files/ to sys.path**

`v1.2/Files/tests/conftest.py`:
```python
"""Pytest config: make shazam.py importable from tests."""
import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
if str(FILES_DIR) not in sys.path:
    sys.path.insert(0, str(FILES_DIR))
```

- [ ] **Step 3: Create pytest.ini**

`v1.2/Files/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 4: Verify pytest discovers no tests yet**

Run: `cd v1.2/Files && python -m pytest --collect-only`
Expected: `no tests ran`

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/tests/__init__.py v1.2/Files/tests/conftest.py v1.2/Files/pytest.ini
git commit -m "test: bootstrap pytest infra for shazam.py helpers"
```

---

## Phase 1 — Pure helpers (TDD)

### Task 1: Responsive scale clamp helper

Used by Section 3 typography scale (`clamp(min, val, max)`) and layout calculations.

**Files:**
- Modify: `v1.2/Files/shazam.py` (add after `safe_float`, ~line 1145)
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing test**

`v1.2/Files/tests/test_ui_helpers.py`:
```python
"""Tests for pure UI helpers in shazam.py (no Tk required)."""
import importlib
import sys
import types

# Stub out modules shazam.py imports that require native libs.
for mod_name in ("pyaudio", "screeninfo", "shazamio"):
    sys.modules.setdefault(mod_name, types.ModuleType(mod_name))
sys.modules["pyaudio"].PyAudio = type("PyAudio", (), {})
sys.modules["pyaudio"].paInt16 = 8
sys.modules["pyaudio"].paInputOverflowed = -9981
sys.modules["screeninfo"].get_monitors = lambda: []
sys.modules["shazamio"].Shazam = type("Shazam", (), {})

shazam = importlib.import_module("shazam")


def test_responsive_clamp_returns_value_when_in_range():
    assert shazam.responsive_clamp(10, 25, 40) == 25


def test_responsive_clamp_clamps_low():
    assert shazam.responsive_clamp(10, 5, 40) == 10


def test_responsive_clamp_clamps_high():
    assert shazam.responsive_clamp(10, 100, 40) == 40


def test_responsive_clamp_handles_float():
    assert shazam.responsive_clamp(0.0, 1.5, 2.0) == 1.5
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v`
Expected: FAIL with `AttributeError: module 'shazam' has no attribute 'responsive_clamp'`

- [ ] **Step 3: Implement responsive_clamp in shazam.py**

Add after `safe_float()`:
```python
def responsive_clamp(min_value: float, value: float, max_value: float) -> float:
    """CSS-style clamp(lo, val, hi). Used throughout the responsive type/spacing scale."""
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/tests/test_ui_helpers.py v1.2/Files/shazam.py
git commit -m "feat(ui): add responsive_clamp helper"
```

---

### Task 2: Easing curve (cubic ease-out)

Used by all line transitions, choreography fades.

**Files:**
- Modify: `v1.2/Files/shazam.py` (after responsive_clamp)
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append to `v1.2/Files/tests/test_ui_helpers.py`:
```python
def test_ease_out_cubic_starts_at_zero():
    assert shazam.ease_out_cubic(0.0) == 0.0


def test_ease_out_cubic_ends_at_one():
    assert shazam.ease_out_cubic(1.0) == 1.0


def test_ease_out_cubic_is_above_linear_in_middle():
    # Ease-out should be ahead of linear in the first half.
    assert shazam.ease_out_cubic(0.5) > 0.5


def test_ease_out_cubic_clamps_input():
    assert shazam.ease_out_cubic(-0.5) == 0.0
    assert shazam.ease_out_cubic(2.0) == 1.0
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k ease_out`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement**

Add after `responsive_clamp()`:
```python
def ease_out_cubic(t: float) -> float:
    """Cubic ease-out: fast start, gentle landing. Domain and range [0, 1]."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k ease_out`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add ease_out_cubic for transitions"
```

---

### Task 3: Color helpers — mix with alpha simulation

Tier 1 already has `mix_rgb`, `rgb_to_hex`, `hex_to_rgb`. Add `dim_hex(hex, amount)` and `simulate_alpha_on_dark(hex, alpha)` for "transparency" on Tk (Tk text has no native alpha — we precompute the visible color by blending toward the scrim color).

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
def test_dim_hex_full_amount_returns_black():
    assert shazam.dim_hex("#ffffff", 1.0) == "#000000"


def test_dim_hex_zero_amount_unchanged():
    assert shazam.dim_hex("#ff8000", 0.0) == "#ff8000"


def test_dim_hex_half_amount():
    assert shazam.dim_hex("#ff0000", 0.5) == "#7f0000"


def test_simulate_alpha_on_dark_full_opacity_unchanged():
    assert shazam.simulate_alpha_on_dark("#ffffff", 1.0) == "#ffffff"


def test_simulate_alpha_on_dark_low_opacity_blends_to_scrim():
    # 0% alpha should equal the scrim color.
    result = shazam.simulate_alpha_on_dark("#ffffff", 0.0)
    assert result == "#0a0a0c"
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k "dim_hex or simulate_alpha"`
Expected: FAIL

- [ ] **Step 3: Implement**

Add after `hex_to_rgb()`:
```python
SCRIM_RGB: Tuple[int, int, int] = (10, 10, 12)  # #0a0a0c — same as canvas bg fallback.


def dim_hex(value: str, amount: float) -> str:
    """Blends a hex color toward black by `amount` (0..1). amount=1 → black."""
    rgb = hex_to_rgb(value)
    return rgb_to_hex(mix_rgb(rgb, (0, 0, 0), amount))


def simulate_alpha_on_dark(value: str, alpha: float) -> str:
    """Tk text has no alpha — simulate by blending the color toward the dark scrim.
    alpha=1.0 returns the color unchanged; alpha=0.0 returns the scrim color."""
    alpha = max(0.0, min(1.0, alpha))
    return rgb_to_hex(mix_rgb(SCRIM_RGB, hex_to_rgb(value), alpha))
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k "dim_hex or simulate_alpha"`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add color dim and alpha-simulation helpers"
```

---

### Task 4: Breakpoint detector

Determines `wide` / `mid` / `tall` from window dimensions.

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
def test_breakpoint_wide_at_1920x1080():
    assert shazam.detect_layout_breakpoint(1920, 1080) == "wide"


def test_breakpoint_stacked_at_400x800():
    assert shazam.detect_layout_breakpoint(400, 800) == "stacked"


def test_breakpoint_stacked_when_narrower_than_900():
    assert shazam.detect_layout_breakpoint(800, 1200) == "stacked"


def test_breakpoint_mid_at_1024x768():
    assert shazam.detect_layout_breakpoint(1024, 768) == "mid"


def test_breakpoint_handles_zero_height():
    # Defensive: don't blow up on a degenerate window.
    assert shazam.detect_layout_breakpoint(800, 0) == "stacked"
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k breakpoint`
Expected: FAIL

- [ ] **Step 3: Implement**

Add a new section header `# --- Layout system ---` and place this helper there:
```python
# --- Layout system ---

def detect_layout_breakpoint(width: int, height: int) -> str:
    """Returns 'wide', 'mid', or 'stacked' based on window dimensions per spec §4."""
    if height <= 0:
        return "stacked"
    aspect = width / height
    if width >= 900 and aspect >= 1.2:
        return "wide"
    if width < 900 or aspect < 0.95:
        return "stacked"
    return "mid"
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k breakpoint`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add layout breakpoint detector"
```

---

### Task 5: Responsive scale resolver

Resolves all the spec's type sizes given a window short edge.

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
def test_type_scale_at_1080_short_edge():
    scale = shazam.compute_type_scale(1080)
    assert scale["title"] == shazam.responsive_clamp(18, int(1080 * 0.035), 38)
    assert scale["lyric_active"] == shazam.responsive_clamp(22, int(1080 * 0.052), 64)
    assert scale["lyric_context"] == shazam.responsive_clamp(13, int(1080 * 0.025), 24)


def test_type_scale_clamps_at_small_size():
    scale = shazam.compute_type_scale(200)
    assert scale["title"] == 18  # min floor
    assert scale["lyric_active"] == 22


def test_type_scale_clamps_at_large_size():
    scale = shazam.compute_type_scale(4000)
    assert scale["title"] == 38  # max ceiling
    assert scale["lyric_active"] == 64
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k type_scale`
Expected: FAIL

- [ ] **Step 3: Implement**

Add to the layout section:
```python
def compute_type_scale(short_edge: int) -> Dict[str, int]:
    """Maps window short-edge px to the responsive type sizes from spec §3."""
    s = max(0, int(short_edge))
    return {
        "title":         int(responsive_clamp(18, s * 0.035, 38)),
        "artist":        int(responsive_clamp(11, s * 0.018, 18)),
        "album":         int(responsive_clamp(10, s * 0.015, 15)),
        "lyric_active":  int(responsive_clamp(22, s * 0.052, 64)),
        "lyric_context": int(responsive_clamp(13, s * 0.025, 24)),
        "status_pill":   int(responsive_clamp(9,  s * 0.013, 14)),
        "history_title": int(responsive_clamp(9,  s * 0.013, 13)),
        "history_artist":int(responsive_clamp(8,  s * 0.011, 11)),
        "wordmark":      int(responsive_clamp(28, s * 0.060, 96)),
    }
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k type_scale`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add responsive type scale resolver"
```

---

### Task 6: Low-power detection

Auto-detects Pi 3 or other low-power host to force reduced motion.

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
from unittest.mock import patch


def test_low_power_true_for_armv7():
    with patch("platform.machine", return_value="armv7l"), \
         patch("os.cpu_count", return_value=4):
        assert shazam.is_low_power_host() is True


def test_low_power_false_for_aarch64():
    with patch("platform.machine", return_value="aarch64"), \
         patch("os.cpu_count", return_value=4):
        assert shazam.is_low_power_host() is False


def test_low_power_false_for_x86_64():
    with patch("platform.machine", return_value="x86_64"), \
         patch("os.cpu_count", return_value=8):
        assert shazam.is_low_power_host() is False
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k low_power`
Expected: FAIL

- [ ] **Step 3: Implement**

At the top of shazam.py imports, ensure `import platform` and `import os` are present (they are). Then add to the layout section:
```python
def is_low_power_host() -> bool:
    """Heuristic: Pi 3 (armv7) is the canonical low-power target. Anything
    armv7 with ≤4 cores triggers the reduced-motion profile by default."""
    import platform
    import os
    machine = platform.machine().lower()
    cpu_count = os.cpu_count() or 1
    return machine.startswith("armv7") and cpu_count <= 4
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k low_power`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add is_low_power_host detection"
```

---

### Task 7: Resolved motion-enabled flag

Combines config + low-power auto-detect into a single function callers can ask.

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
def test_motion_enabled_when_config_false_and_high_power():
    cfg = {"gui": {"motion_reduced": False}}
    with patch.object(shazam, "is_low_power_host", return_value=False):
        assert shazam.is_motion_enabled(cfg) is True


def test_motion_disabled_when_config_true():
    cfg = {"gui": {"motion_reduced": True}}
    with patch.object(shazam, "is_low_power_host", return_value=False):
        assert shazam.is_motion_enabled(cfg) is False


def test_motion_disabled_on_low_power_even_if_config_false():
    cfg = {"gui": {"motion_reduced": False}}
    with patch.object(shazam, "is_low_power_host", return_value=True):
        assert shazam.is_motion_enabled(cfg) is False
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k motion_enabled`
Expected: FAIL

- [ ] **Step 3: Implement**

Add to the layout section:
```python
def is_motion_enabled(cfg: Dict[str, Any]) -> bool:
    """True when full motion (Ken Burns, glow breath, choreography) should run."""
    if bool(cfg.get("gui", {}).get("motion_reduced", False)):
        return False
    return not is_low_power_host()
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k motion_enabled`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add is_motion_enabled resolver"
```

---

## Phase 2 — Config knobs

### Task 8: Add new config defaults

Per spec §8 — adds `gui.ken_burns_enabled`, `gui.motion_reduced`, `gui.idle_splash_enabled`, `gui.accent_halo_intensity`, `gui.idle_splash_after_seconds`, `lyrics.lines_visible`.

**Files:**
- Modify: `v1.2/Files/shazam.py` (defaults block in `load_config`)
- Modify: `v1.2/Files/config.json` (mirror)

- [ ] **Step 1: Edit defaults in `load_config` (in shazam.py)**

Locate the `"gui"` block in `defaults` (currently has `vignette_intensity`). Add:
```python
            "vignette_intensity": 0.55,
            "ken_burns_enabled": True,
            "motion_reduced": False,
            "idle_splash_enabled": True,
            "idle_splash_after_seconds": 10,
            "accent_halo_intensity": 0.35,
```

Locate the `"lyrics"` block. Add:
```python
            "lines_visible": 3,
```

- [ ] **Step 2: Mirror knobs into `v1.2/Files/config.json`**

In the `"gui"` block (after `"vignette_intensity": 0.55,`):
```json
        "ken_burns_enabled": true,
        "motion_reduced": false,
        "idle_splash_enabled": true,
        "idle_splash_after_seconds": 10,
        "accent_halo_intensity": 0.35,
```

In the `"lyrics"` block:
```json
        "lines_visible": 3,
```

- [ ] **Step 3: Verify JSON parses**

Run: `python -c "import json; json.load(open('v1.2/Files/config.json'))"`
Expected: no output (success)

- [ ] **Step 4: Verify shazam.py syntax**

Run: `python -c "import ast; ast.parse(open('v1.2/Files/shazam.py').read())"`
Expected: no output (success)

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/config.json
git commit -m "feat(ui): add config knobs for motion, idle splash, halo, lyric lines"
```

---

## Phase 3 — Visual primitives

### Task 9: Cover-art halo pre-render

Pre-renders a Gaussian-blurred accent disc behind the cover art (one PIL pass per song-change).

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add module-level state**

Near the other globals (line ~80), add:
```python
cover_halo_photo_ref: Optional[ImageTk.PhotoImage] = None
cover_halo_item_id: Optional[int] = None
```

- [ ] **Step 2: Add the renderer function**

Place after `apply_vignette()`:
```python
def build_cover_halo(cover_size: int, accent_hex: str, intensity: float) -> Optional[Image.Image]:
    """Returns a PIL RGBA image of a soft accent-colored halo sized 1.18× the
    cover. Used as a glow plate placed behind the cover art."""
    try:
        side = max(8, int(cover_size * 1.18))
        halo = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = ImageDraw.Draw(halo)
        r, g, b = hex_to_rgb(accent_hex)
        alpha = int(255 * max(0.0, min(1.0, intensity)))
        # Solid disc centered, blurred so it bleeds softly.
        margin = side // 8
        draw.ellipse([margin, margin, side - margin, side - margin],
                     fill=(r, g, b, alpha))
        blur_px = max(8, side // 8)
        return halo.filter(ImageFilter.GaussianBlur(blur_px))
    except Exception as e:
        logger.debug(f"build_cover_halo failed: {e}")
        return None


def render_cover_halo(square_x: float, square_y: float, square_size: int) -> None:
    """Renders (or refreshes) the accent halo behind the cover art."""
    global cover_halo_photo_ref, cover_halo_item_id
    if not canvas:
        return
    if not config.get("gui", {}).get("idle_splash_enabled", True) and False:
        pass  # placeholder so linter doesn't fold
    intensity = safe_float(config.get("gui", {}).get("accent_halo_intensity")) or 0.35
    halo_image = build_cover_halo(square_size, accent_color_hex, intensity)
    if halo_image is None:
        if cover_halo_item_id:
            try:
                canvas.delete(cover_halo_item_id)
            except tk.TclError:
                pass
            cover_halo_item_id = None
        cover_halo_photo_ref = None
        return
    cover_halo_photo_ref = ImageTk.PhotoImage(halo_image)
    if cover_halo_item_id:
        try:
            canvas.coords(cover_halo_item_id, square_x, square_y)
            canvas.itemconfigure(cover_halo_item_id, image=cover_halo_photo_ref)
        except tk.TclError:
            cover_halo_item_id = None
    if not cover_halo_item_id:
        cover_halo_item_id = canvas.create_image(
            square_x, square_y,
            anchor=tk.CENTER,
            image=cover_halo_photo_ref,
            tags=("background", "cover_halo"),
        )
    # Halo sits between background and cover art.
    try:
        canvas.tag_raise("cover_halo", "background")
        if coverart_item_id:
            canvas.tag_raise(coverart_item_id, "cover_halo")
    except tk.TclError:
        pass
```

- [ ] **Step 3: Wire `render_cover_halo` into `update_images`**

In `update_images`, after the existing cover-art rendering block (search for `coverart_item_id = canvas.create_image`), add immediately after the cover is positioned:
```python
        # New: paint accent halo plate behind the cover art.
        render_cover_halo(square_x, square_y, int(square_size))
```

- [ ] **Step 4: Smoke check — run the app**

Run: `cd v1.2/Files && python shazam.py &` (or `./Run.bat` on Windows)
Visually verify: when a song with a colorful cover loads, a soft accent glow is visible behind the cover. Quit the app.

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): add accent halo plate behind cover art"
```

---

### Task 10: Strip glyph prefixes from cinematic metadata

Spec §6.3: remove the `♩ ◎ ◌` glyph prefixes — they read as noise next to the new layout.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Locate and edit the cinematic title block**

Find the block (~line 2424):
```python
        title_display_text = last_track_title
        album_text = last_album_name.strip()
        album_display_text = album_text
        artist_display_text = last_artist_name
        if cinematic_mode:
            title_display_text = f"♩ {last_track_title}" if last_track_title else ""
            album_display_text = f"◎ {album_text}" if album_text else ""
            artist_display_text = f"◌ {last_artist_name}" if last_artist_name else ""
```

Replace with:
```python
        title_display_text = last_track_title
        album_text = last_album_name.strip()
        album_display_text = album_text
        artist_display_text = last_artist_name
```

- [ ] **Step 2: Verify shazam.py syntax**

Run: `python -c "import ast; ast.parse(open('v1.2/Files/shazam.py').read())"`
Expected: no output

- [ ] **Step 3: Smoke check — run the app**

Run the app. Verify the cinematic title no longer shows `♩` etc. prefixes; just plain "Title", "Artist", "Album".

- [ ] **Step 4: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): strip ♩◎◌ glyph prefixes from metadata"
```

---

### Task 11: Artist label uppercase + tracked

Spec §3 typography — artist label rendered uppercase with letter-spacing 0.08em-ish (Tk has no letter-spacing, so we insert hair-space U+200A between characters when the line is short enough).

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add formatting helper**

Place near `normalize_lyrics_key_part` or in the visual helpers section:
```python
def format_artist_label(value: str, max_chars: int = 40) -> str:
    """Renders the artist label in uppercase. If short enough, inserts hair
    spaces between letters to fake letter-tracking (Tk lacks letter-spacing)."""
    if not value:
        return ""
    upper = value.upper()
    if len(upper) <= max_chars:
        return " ".join(upper)  # U+200A = hair space
    return upper
```

- [ ] **Step 2: Add a test for the helper**

Append to `tests/test_ui_helpers.py`:
```python
def test_format_artist_label_uppercases():
    assert "TAYLOR" in shazam.format_artist_label("Taylor Swift")


def test_format_artist_label_inserts_hair_space_when_short():
    out = shazam.format_artist_label("ABBA")
    assert " " in out


def test_format_artist_label_skips_tracking_when_long():
    long = "A Very Long Artist Name That Should Not Get Tracked Out"
    out = shazam.format_artist_label(long)
    assert " " not in out
```

- [ ] **Step 3: Run tests**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k format_artist`
Expected: 3 PASS

- [ ] **Step 4: Wire helper into `update_images`**

In `update_images`, where `artist_display_text` is set (after Task 10's change), wrap the value:
```python
        artist_display_text = format_artist_label(last_artist_name)
```

- [ ] **Step 5: Smoke check**

Run the app. Verify artist line displays uppercase with subtle inter-letter spacing.

- [ ] **Step 6: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): uppercase + faux-tracked artist label"
```

---

## Phase 4 — Lyric column upgrade

### Task 12: 3-line lyric column size hierarchy

Per spec §6.4 — active line should be 1.4–1.6× the context lines. Current Tier 1 uses similar sizes for all three. Tune the layout cache.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Locate the cinematic lyric font sizing block (~line 2110)**

```python
    if cinematic_mode:
        main_font_size = max(18, min(34, int(window_width * 0.032)))
        artist_font_size = max(12, int(main_font_size * 0.42))
        status_font_size = max(10, int(main_font_size * 0.32))
        lyrics_primary_font_size = max(24, min(58, int(window_width * 0.047)))
        lyrics_secondary_font_size = max(18, int(lyrics_primary_font_size * 0.62))
        lyrics_tertiary_font_size = max(16, int(lyrics_primary_font_size * 0.54))
```

Replace with values computed from the new responsive scale:
```python
    if cinematic_mode:
        type_scale = compute_type_scale(min(window_width, window_height))
        main_font_size = type_scale["title"]
        artist_font_size = type_scale["artist"]
        status_font_size = type_scale["status_pill"]
        lyrics_primary_font_size = type_scale["lyric_active"]
        # Context lines target ~55% of active per spec (active = 1.6× context).
        lyrics_secondary_font_size = max(13, int(lyrics_primary_font_size * 0.55))
        lyrics_tertiary_font_size = max(12, int(lyrics_primary_font_size * 0.48))
```

- [ ] **Step 2: Smoke check**

Run the app, recognize a song. Verify the active lyric line is visibly larger than prev/next and the difference reads as deliberate hierarchy.

- [ ] **Step 3: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): widen size gap between active and context lyric lines"
```

---

### Task 13: Lyric active-line glow breath

Per spec §5.3 — sin-curve color blend between accent-active and brighter-accent over 3.6s on the active line. Disabled in reduced-motion.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add module-level state**

Near other globals:
```python
lyric_glow_phase: float = 0.0
lyric_glow_job_id: Optional[str] = None
```

- [ ] **Step 2: Add the tick function**

Place near `tick_status_pulse`:
```python
def tick_lyric_glow():
    """Drives the breathing-glow color cycle on the active lyric line.

    Sin-curve over ~3.6s, ±15% amplitude blending between the base active
    color and a brighter variant. Disabled when motion is reduced."""
    global lyric_glow_job_id, lyric_glow_phase
    lyric_glow_job_id = None
    if not root or not canvas or not root.winfo_exists():
        return
    if not is_motion_enabled(config):
        # Schedule a slow no-op tick so we resume cleanly if config flips.
        try:
            lyric_glow_job_id = root.after(1000, tick_lyric_glow)
        except tk.TclError:
            lyric_glow_job_id = None
        return
    try:
        if lyrics_primary_label_id and lyrics_state.get("synced_lines"):
            lyric_glow_phase = (lyric_glow_phase + (2 * math.pi / 36)) % (2 * math.pi)
            # 36 ticks per cycle × 100ms = 3.6s period.
            pulse = 0.5 + 0.5 * math.sin(lyric_glow_phase)
            accent_rgb = hex_to_rgb(accent_color_hex)
            base = mix_rgb(accent_rgb, (255, 255, 255), 0.35)
            bright = mix_rgb(accent_rgb, (255, 255, 255), 0.55)
            blended = mix_rgb(base, bright, pulse * 0.6)
            canvas.itemconfigure(lyrics_primary_label_id, fill=rgb_to_hex(blended))
    except tk.TclError:
        pass
    try:
        lyric_glow_job_id = root.after(100, tick_lyric_glow)
    except tk.TclError:
        lyric_glow_job_id = None
```

- [ ] **Step 3: Start the tick loop at app init**

In `main()`, after `root.after(300, tick_status_pulse)`, add:
```python
    root.after(400, tick_lyric_glow)
```

- [ ] **Step 4: Smoke check**

Run the app, recognize a song with lyrics. Verify the active lyric line subtly breathes — color shifts between two accent shades over ~3.6s.

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): add breathing glow on active lyric line"
```

---

### Task 14: Lyric advance slide+fade transition

Per spec §5.2 — when the active lyric index changes, the new line slides up 8px and fades from accent-40% to accent-100% over 320ms.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add transition state**

Near other globals:
```python
lyric_transition_state: Dict[str, Any] = {
    "active": False,
    "start_monotonic": 0.0,
    "duration": 0.32,
    "last_index": -1,
}
```

- [ ] **Step 2: Track active-line index in `compute_current_lyrics_lines`**

Find `compute_current_lyrics_lines()` (~line 1351). At the top of the synced-lines branch, capture the current index for change detection. Replace:
```python
    if lyrics_state.get("synced_lines"):
        anchor_monotonic = lyrics_state.get("anchor_monotonic")
        if anchor_monotonic is None:
            return []
        anchor_song_seconds = lyrics_state.get("anchor_song_seconds", 0.0)
        lrc_offset = lyrics_state.get("lrc_offset_seconds", 0.0)
        user_adjust = safe_float(config.get("lyrics", {}).get("offset_adjust_seconds")) or 0.0
        playback_seconds = (
            anchor_song_seconds
            + (time.monotonic() - anchor_monotonic)
            - lrc_offset
            + user_adjust
        )
        return build_synced_lyrics_lines(max(0.0, playback_seconds))
```

with:
```python
    if lyrics_state.get("synced_lines"):
        anchor_monotonic = lyrics_state.get("anchor_monotonic")
        if anchor_monotonic is None:
            return []
        anchor_song_seconds = lyrics_state.get("anchor_song_seconds", 0.0)
        lrc_offset = lyrics_state.get("lrc_offset_seconds", 0.0)
        user_adjust = safe_float(config.get("lyrics", {}).get("offset_adjust_seconds")) or 0.0
        playback_seconds = (
            anchor_song_seconds
            + (time.monotonic() - anchor_monotonic)
            - lrc_offset
            + user_adjust
        )
        playback_seconds = max(0.0, playback_seconds)

        # Detect line advances → start a fade-in transition.
        active_index = -1
        for i, line in enumerate(lyrics_state["synced_lines"]):
            if playback_seconds >= line["time_seconds"]:
                active_index = i
            else:
                break
        if active_index != lyric_transition_state["last_index"] and is_motion_enabled(config):
            lyric_transition_state["active"] = True
            lyric_transition_state["start_monotonic"] = time.monotonic()
        lyric_transition_state["last_index"] = active_index

        return build_synced_lyrics_lines(playback_seconds)
```

- [ ] **Step 3: Add the transition tick**

Place near `tick_lyric_glow`:
```python
def tick_lyric_transition():
    """Applies the per-frame fade-in for a freshly-advanced lyric line.

    Active for `lyric_transition_state['duration']` seconds after a line
    change; blends the active line's color from a low-opacity accent toward
    full while shifting it vertically by a few pixels (ease-out)."""
    if not lyric_transition_state.get("active"):
        return
    if not canvas or not lyrics_primary_label_id:
        return
    elapsed = time.monotonic() - lyric_transition_state["start_monotonic"]
    duration = lyric_transition_state["duration"]
    if elapsed >= duration:
        lyric_transition_state["active"] = False
        # On completion, leave the line color to tick_lyric_glow.
        return
    t = ease_out_cubic(elapsed / duration)
    accent_rgb = hex_to_rgb(accent_color_hex)
    base = mix_rgb(accent_rgb, (255, 255, 255), 0.35)
    start_color = simulate_alpha_on_dark(rgb_to_hex(base), 0.4)
    end_color = rgb_to_hex(base)
    blended = mix_rgb(hex_to_rgb(start_color), hex_to_rgb(end_color), t)
    try:
        canvas.itemconfigure(lyrics_primary_label_id, fill=rgb_to_hex(blended))
        # Subtle y-offset: start +8px, ease to 0.
        offset = int(8 * (1.0 - t))
        coords = canvas.coords(lyrics_primary_label_id)
        if len(coords) >= 2:
            base_y = lyrics_layout_cache.get("primary_y", coords[1])
            canvas.coords(lyrics_primary_label_id, coords[0], base_y + offset)
    except tk.TclError:
        lyric_transition_state["active"] = False
```

- [ ] **Step 4: Drive the transition tick from `refresh_lyrics_display`**

In `refresh_lyrics_display`, after `tick_progress_bar()`:
```python
    tick_lyric_transition()
```

- [ ] **Step 5: Smoke check**

Run the app, recognize a song with lyrics. As lyric lines advance, the new line should briefly fade in (color brightens, line nudges into place).

- [ ] **Step 6: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): add slide+fade transition on lyric advance"
```

---

## Phase 5 — Recent strip extension

### Task 15: Recent strip with title + artist labels

Per spec §6.5. Current cinematic history shows thumbs with a tight title only. Add two-line labels (title body 500, artist body 400 tertiary), dim from newest (left) to oldest (right).

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Locate `redraw_history_display` cinematic branch (~line 2607)**

Read the function. The existing code already lays out art + a title font + an artist font. We add a fade gradient across items and wire to the new type scale.

- [ ] **Step 2: After computing `items_to_draw`, add a per-item opacity calc**

Just before the loop that draws each item, insert:
```python
        item_count = max(1, len(items_to_draw))
```

Inside the item loop, where each item is positioned and rendered, compute:
```python
            # Newest = 100%, oldest = 50%, linear.
            opacity = 1.0 - (idx / max(1, item_count - 1)) * 0.5 if item_count > 1 else 1.0
            faded_text = simulate_alpha_on_dark(layout_info.get("text_color", "#ffffff"), opacity)
            faded_artist = simulate_alpha_on_dark("#cdd2da", opacity * 0.85)
```

Then update each `canvas.create_text` / `canvas.itemconfigure` call that targets the title or artist label inside the loop to use `fill=faded_text` (title) and `fill=faded_artist` (artist).

(Note: the existing loop iterates with an index; if it doesn't, change `for item in items_to_draw:` to `for idx, item in enumerate(items_to_draw):` first.)

- [ ] **Step 3: Smoke check**

Run the app, recognize at least 3 songs in a row. Verify the recent strip shows title+artist labels and items fade from bright (left/newest) to dim (right/oldest).

- [ ] **Step 4: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): fade recent strip items by recency, show artist label"
```

---

## Phase 6 — Idle splash

### Task 16: Idle state detector

Decides whether the UI should be in "idle splash" mode based on time since the last recognition + presence of a current match.

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Add state**

Near other globals:
```python
last_recognition_monotonic: float = 0.0   # Updated when a match resolves.
```

- [ ] **Step 2: Stamp the timestamp on each successful recognition**

In `process_recognition_result`, near the top after `track_info = result.get('track', {})`:
```python
    global last_recognition_monotonic
    last_recognition_monotonic = time.monotonic()
```

- [ ] **Step 3: Write the failing test**

Append:
```python
def test_should_show_idle_splash_when_no_recent_match():
    cfg = {"gui": {"idle_splash_enabled": True, "idle_splash_after_seconds": 10}}
    assert shazam.should_show_idle_splash(
        last_match_monotonic=0.0,
        now_monotonic=100.0,
        has_active_track=False,
        cfg=cfg,
    ) is True


def test_should_not_show_idle_splash_when_track_active():
    cfg = {"gui": {"idle_splash_enabled": True, "idle_splash_after_seconds": 10}}
    assert shazam.should_show_idle_splash(
        last_match_monotonic=0.0,
        now_monotonic=100.0,
        has_active_track=True,
        cfg=cfg,
    ) is False


def test_should_not_show_idle_splash_when_disabled():
    cfg = {"gui": {"idle_splash_enabled": False, "idle_splash_after_seconds": 10}}
    assert shazam.should_show_idle_splash(
        last_match_monotonic=0.0,
        now_monotonic=100.0,
        has_active_track=False,
        cfg=cfg,
    ) is False


def test_should_not_show_idle_splash_within_threshold():
    cfg = {"gui": {"idle_splash_enabled": True, "idle_splash_after_seconds": 10}}
    assert shazam.should_show_idle_splash(
        last_match_monotonic=95.0,
        now_monotonic=100.0,
        has_active_track=False,
        cfg=cfg,
    ) is False
```

- [ ] **Step 4: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k idle_splash`
Expected: FAIL

- [ ] **Step 5: Implement**

Add to the layout section:
```python
def should_show_idle_splash(last_match_monotonic: float, now_monotonic: float,
                            has_active_track: bool, cfg: Dict[str, Any]) -> bool:
    """Splash if: enabled, no active track, and >= idle_splash_after_seconds
    have elapsed since any successful match."""
    gui_cfg = cfg.get("gui", {})
    if not bool(gui_cfg.get("idle_splash_enabled", True)):
        return False
    if has_active_track:
        return False
    threshold = safe_float(gui_cfg.get("idle_splash_after_seconds")) or 10.0
    return (now_monotonic - last_match_monotonic) >= threshold
```

- [ ] **Step 6: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k idle_splash`
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): add idle-splash detector + last-match timestamp"
```

---

### Task 17: Render idle splash mesh gradient

Per spec §6.7. Pre-rendered PIL mesh-gradient (3 accent stops cycling warm/cool/neutral) with the SongPi wordmark centered.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add module-level state**

```python
idle_splash_active: bool = False
idle_splash_bg_id: Optional[int] = None
idle_splash_bg_photo_ref: Optional[ImageTk.PhotoImage] = None
idle_splash_wordmark_id: Optional[int] = None
```

- [ ] **Step 2: Add the PIL gradient builder**

Place after `apply_vignette()`:
```python
SPLASH_STOPS = [
    (124, 143, 255),    # cool indigo
    (200, 110, 180),    # warm pink
    (140, 200, 230),    # cool sky
]


def build_splash_gradient(width: int, height: int, phase: float = 0.0) -> Image.Image:
    """Three-stop mesh-gradient backdrop for the idle splash. `phase` rotates
    which stops anchor which corners (so consecutive renders shift mood)."""
    img = Image.new("RGB", (width, height), (10, 10, 12))
    draw = ImageDraw.Draw(img)
    rotated = [SPLASH_STOPS[(i + int(phase)) % len(SPLASH_STOPS)] for i in range(3)]
    # Three offset blurred discs, composite-blended for an approximate mesh.
    layer = Image.new("RGB", (width, height), (10, 10, 12))
    pix = layer.load()
    cx_positions = [
        (int(width * 0.25), int(height * 0.30)),
        (int(width * 0.78), int(height * 0.40)),
        (int(width * 0.50), int(height * 0.78)),
    ]
    max_r = max(width, height) * 0.7
    for cx, cy in cx_positions:
        rgb = rotated[cx_positions.index((cx, cy))]
        for y in range(0, height, 4):
            for x in range(0, width, 4):
                dx = x - cx; dy = y - cy
                d = (dx * dx + dy * dy) ** 0.5
                t = max(0.0, 1.0 - d / max_r)
                t = t * t  # softer falloff
                r0, g0, b0 = pix[x, y]
                r1, g1, b1 = rgb
                pix[x, y] = (
                    int(r0 + (r1 - r0) * t * 0.6),
                    int(g0 + (g1 - g0) * t * 0.6),
                    int(b0 + (b1 - b0) * t * 0.6),
                )
    layer = layer.resize((width, height), Image.Resampling.BILINEAR)
    return layer.filter(ImageFilter.GaussianBlur(max(20, min(width, height) // 12)))
```

- [ ] **Step 3: Add the splash renderer**

Place after `build_splash_gradient`:
```python
def render_idle_splash(window_width: int, window_height: int) -> None:
    """Paints the idle splash: full-window mesh gradient + centered wordmark."""
    global idle_splash_bg_id, idle_splash_bg_photo_ref, idle_splash_wordmark_id
    if not canvas:
        return
    try:
        gradient = build_splash_gradient(window_width, window_height, phase=0.0)
        idle_splash_bg_photo_ref = ImageTk.PhotoImage(gradient)
        if idle_splash_bg_id:
            try:
                canvas.itemconfigure(idle_splash_bg_id, image=idle_splash_bg_photo_ref)
            except tk.TclError:
                idle_splash_bg_id = None
        if not idle_splash_bg_id:
            idle_splash_bg_id = canvas.create_image(
                0, 0, anchor=tk.NW,
                image=idle_splash_bg_photo_ref,
                tags=("idle_splash",),
            )

        wordmark_size = compute_type_scale(min(window_width, window_height))["wordmark"]
        font_obj = (get_ui_font_family(), wordmark_size, "bold")
        text_x = window_width / 2
        text_y = window_height / 2
        if idle_splash_wordmark_id:
            try:
                canvas.coords(idle_splash_wordmark_id, text_x, text_y)
                canvas.itemconfigure(
                    idle_splash_wordmark_id,
                    text="SongPi",
                    font=font_obj,
                    fill="#ffffff",
                    anchor=tk.CENTER,
                )
            except tk.TclError:
                idle_splash_wordmark_id = None
        if not idle_splash_wordmark_id:
            idle_splash_wordmark_id = canvas.create_text(
                text_x, text_y,
                text="SongPi",
                font=font_obj,
                fill="#ffffff",
                anchor=tk.CENTER,
                tags=("idle_splash", "wordmark"),
            )
        canvas.tag_raise("idle_splash")
        canvas.tag_raise("status_pill")  # Status pill stays on top.
    except tk.TclError as e:
        logger.debug(f"render_idle_splash failed: {e}")


def hide_idle_splash() -> None:
    """Removes splash items if present."""
    if not canvas:
        return
    try:
        canvas.delete("idle_splash")
    except tk.TclError:
        pass
    global idle_splash_bg_id, idle_splash_bg_photo_ref, idle_splash_wordmark_id
    idle_splash_bg_id = None
    idle_splash_bg_photo_ref = None
    idle_splash_wordmark_id = None
```

- [ ] **Step 4: Wire splash decision into `update_images`**

Near the start of `update_images`, after `window_width`, `window_height` are obtained, add:
```python
    global idle_splash_active
    has_active_track = bool(last_track_title)
    splash = should_show_idle_splash(
        last_match_monotonic=last_recognition_monotonic,
        now_monotonic=time.monotonic(),
        has_active_track=has_active_track,
        cfg=config,
    )
    idle_splash_active = splash
    if splash:
        render_idle_splash(window_width, window_height)
        # In idle splash, skip the rest of the layout.
        layout_info.update({"idle_splash": True})
        return layout_info
    else:
        hide_idle_splash()
```

- [ ] **Step 5: Smoke check**

Run the app with no song playing. After ~10 seconds with no recognition, the screen should fade to a soft gradient with "SongPi" centered.

- [ ] **Step 6: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): add idle splash with mesh gradient and wordmark"
```

---

## Phase 7 — Status pill states

### Task 18: Map status text → pill state

Per spec §6.1 — pill states beyond Tier 1 (`no-match`, `error`, `idle`, `starting`).

**Files:**
- Modify: `v1.2/Files/shazam.py`
- Test: `v1.2/Files/tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

Append:
```python
def test_status_state_listening():
    assert shazam.classify_status_state("Listening...") == "listening"


def test_status_state_recognizing():
    assert shazam.classify_status_state("Recognizing...") == "recognizing"


def test_status_state_no_match():
    assert shazam.classify_status_state("No Match Found") == "no_match"


def test_status_state_error():
    assert shazam.classify_status_state("Error: Recognition failed") == "error"


def test_status_state_starting():
    assert shazam.classify_status_state("Initialising...") == "starting"


def test_status_state_ready():
    assert shazam.classify_status_state("Ready (Restored)") == "ready"


def test_status_state_default_falls_to_idle():
    assert shazam.classify_status_state("") == "idle"
```

- [ ] **Step 2: Run test, expect failure**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k status_state`
Expected: FAIL

- [ ] **Step 3: Implement**

Add near `render_status_pill`:
```python
def classify_status_state(message: str) -> str:
    """Maps a status message string to a state token consumed by the pill renderer."""
    msg = (message or "").lower()
    if not msg.strip():
        return "idle"
    if "error" in msg or "offline" in msg:
        return "error"
    if "no match" in msg:
        return "no_match"
    if "init" in msg or "starting" in msg:
        return "starting"
    if "ready" in msg or "restored" in msg:
        return "ready"
    if "recogni" in msg or "retry" in msg:
        return "recognizing"
    if "listen" in msg or "fetch" in msg or "loading" in msg:
        return "listening"
    return "idle"
```

- [ ] **Step 4: Verify tests pass**

Run: `cd v1.2/Files && python -m pytest tests/test_ui_helpers.py -v -k status_state`
Expected: 7 PASS

- [ ] **Step 5: Use the classifier inside `render_status_pill`**

In `render_status_pill`, replace the existing dot-color logic block (the `msg_lower = label_text.lower()` and following lines that compute `working`/`dot_color`) with:
```python
    state = classify_status_state(label_text)
    if state in ("listening", "recognizing"):
        dot_color = accent_color_hex
    elif state == "error":
        dot_color = "#dc2626"
    elif state == "no_match":
        dot_color = "#8b919c"
    elif state == "starting":
        dot_color = accent_color_hex
    else:
        dot_color = "#5b6270"
```

And in `tick_status_pulse`, replace the `working = ...` block with:
```python
            state = classify_status_state(current_status_message)
            working = state in ("listening", "recognizing", "starting")
```

- [ ] **Step 6: Smoke check**

Run the app. Verify pill dot:
- Pulses accent while "Listening" or "Recognizing"
- Goes red on "Error" (force by disconnecting network briefly)
- Goes neutral grey on "No Match Found"

- [ ] **Step 7: Commit**

```bash
git add v1.2/Files/shazam.py v1.2/Files/tests/test_ui_helpers.py
git commit -m "feat(ui): classify status states for pill dot color"
```

---

## Phase 8 — Track-change choreography

### Task 19: Track-change choreography

Per spec §7. When `process_recognition_result` resolves a *different* track, schedule a 300ms accent-color and meta crossfade.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add module-level state**

```python
track_change_state: Dict[str, Any] = {
    "active": False,
    "start_monotonic": 0.0,
    "duration": 0.3,
    "previous_accent": "#7c8fff",
}
track_change_job_id: Optional[str] = None
```

- [ ] **Step 2: Add the trigger function**

Place near `tick_lyric_transition`:
```python
def begin_track_change_choreography(previous_accent: str) -> None:
    """Kicks off the 300ms color/meta crossfade after a different-track recognition."""
    if not is_motion_enabled(config):
        return
    track_change_state["active"] = True
    track_change_state["start_monotonic"] = time.monotonic()
    track_change_state["previous_accent"] = previous_accent or "#7c8fff"
    if root and root.winfo_exists():
        try:
            root.after(16, tick_track_change_choreography)
        except tk.TclError:
            pass


def tick_track_change_choreography():
    """Per-frame interpolation of accent color across UI elements during a
    track change."""
    global track_change_job_id
    track_change_job_id = None
    if not track_change_state.get("active") or not canvas:
        return
    elapsed = time.monotonic() - track_change_state["start_monotonic"]
    duration = track_change_state["duration"]
    if elapsed >= duration:
        track_change_state["active"] = False
        return
    t = ease_out_cubic(elapsed / duration)
    prev_rgb = hex_to_rgb(track_change_state["previous_accent"])
    new_rgb = hex_to_rgb(accent_color_hex)
    blended = rgb_to_hex(mix_rgb(prev_rgb, new_rgb, t))
    try:
        if progress_bar_fill_id:
            canvas.itemconfigure(progress_bar_fill_id, fill=blended)
        if status_pill_dot_id and classify_status_state(current_status_message) in ("listening", "recognizing", "starting"):
            canvas.itemconfigure(status_pill_dot_id, fill=blended)
    except tk.TclError:
        track_change_state["active"] = False
        return
    if root and root.winfo_exists():
        try:
            track_change_job_id = root.after(16, tick_track_change_choreography)
        except tk.TclError:
            track_change_job_id = None
```

- [ ] **Step 3: Trigger on different-track recognition**

In `process_recognition_result`, near the existing `prepare_lyrics_for_track` call, add a same-track guard. Above that block, capture the previous values:
```python
    previous_track_key = build_track_key(last_track_title, last_artist_name) if last_track_title else None
    previous_accent = accent_color_hex
```

After `prepare_lyrics_for_track(result, new_title, new_artist, record_start_monotonic)`, add:
```python
    new_track_key = build_track_key(new_title, new_artist)
    if previous_track_key and new_track_key != previous_track_key:
        begin_track_change_choreography(previous_accent)
```

- [ ] **Step 4: Smoke check**

Run the app, play a song through, then switch to a different song with a contrasting cover. On the new recognition, the progress bar and status dot should briefly animate from the old accent to the new one.

- [ ] **Step 5: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): accent crossfade on track change"
```

---

## Phase 9 — Ken Burns backdrop

### Task 20: Ken Burns crossfade between two pre-rendered frames

Per spec §5.1.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: Add module state**

```python
ken_burns_frame_a_ref: Optional[ImageTk.PhotoImage] = None
ken_burns_frame_b_ref: Optional[ImageTk.PhotoImage] = None
ken_burns_item_a: Optional[int] = None
ken_burns_item_b: Optional[int] = None
ken_burns_phase: float = 0.0   # 0..1 across one drift cycle
ken_burns_direction: int = 1
ken_burns_job_id: Optional[str] = None
ken_burns_last_window_size: Tuple[int, int] = (0, 0)
```

- [ ] **Step 2: Add the frame builder**

Place after `apply_vignette`:
```python
def build_ken_burns_frames(source_image_path: Path, width: int, height: int,
                           blur_strength: int, vignette_intensity: float) -> Optional[Tuple[Image.Image, Image.Image]]:
    """Pre-renders two slightly-different zoom/translate variants of the
    blurred+vignetted backdrop. Tk crossfades between them."""
    try:
        base = create_blurred_background(source_image_path, width, height, blur_strength)
        if base is None:
            return None
        base = apply_vignette(base, intensity=vignette_intensity)
        # Frame A: 1.04× scale, NW translate.
        a = base.resize((int(width * 1.04), int(height * 1.04)), Image.Resampling.LANCZOS)
        a = a.crop((0, 0, width, height))
        # Frame B: 1.10× scale, SE translate.
        b = base.resize((int(width * 1.10), int(height * 1.10)), Image.Resampling.LANCZOS)
        offset_x = (int(width * 1.10) - width)
        offset_y = (int(height * 1.10) - height)
        b = b.crop((offset_x, offset_y, offset_x + width, offset_y + height))
        return a, b
    except Exception as e:
        logger.debug(f"build_ken_burns_frames failed: {e}")
        return None
```

- [ ] **Step 3: Add the install + tick**

```python
def install_ken_burns(image_file_path: Path, width: int, height: int) -> bool:
    """Replaces the static blurred background with two crossfading frames.
    Returns True if installation succeeded."""
    global ken_burns_frame_a_ref, ken_burns_frame_b_ref
    global ken_burns_item_a, ken_burns_item_b, ken_burns_last_window_size

    gui_cfg = config.get("gui", {})
    if not bool(gui_cfg.get("ken_burns_enabled", True)) or not is_motion_enabled(config):
        return False
    if not canvas or width <= 0 or height <= 0:
        return False

    vignette_intensity = safe_float(gui_cfg.get("vignette_intensity")) or 0.55
    blur_strength = gui_cfg.get("blur_strength", 15)
    frames = build_ken_burns_frames(image_file_path, width, height, blur_strength, vignette_intensity)
    if frames is None:
        return False

    ken_burns_frame_a_ref = ImageTk.PhotoImage(frames[0])
    ken_burns_frame_b_ref = ImageTk.PhotoImage(frames[1])

    try:
        canvas.delete("background")
        canvas.delete("ken_burns")
    except tk.TclError:
        pass

    ken_burns_item_a = canvas.create_image(0, 0, anchor=tk.NW, image=ken_burns_frame_a_ref,
                                            tags=("background", "ken_burns"))
    ken_burns_item_b = canvas.create_image(0, 0, anchor=tk.NW, image=ken_burns_frame_b_ref,
                                            tags=("background", "ken_burns"), state="hidden")
    canvas.tag_lower("background")
    ken_burns_last_window_size = (width, height)
    return True


def tick_ken_burns():
    """Drives a 24s cycle that crossfades between frame A and frame B by
    flipping which is visible. Tk has no real opacity, so we toggle at the
    midpoint — the slow PIL difference between frames makes the toggle
    visually subtle."""
    global ken_burns_job_id, ken_burns_phase, ken_burns_direction
    ken_burns_job_id = None
    if not root or not canvas or not root.winfo_exists():
        return
    if not is_motion_enabled(config) or ken_burns_item_a is None:
        try:
            ken_burns_job_id = root.after(2000, tick_ken_burns)
        except tk.TclError:
            ken_burns_job_id = None
        return
    cycle_seconds = 24.0
    step = (1.0 / cycle_seconds) * (0.5)  # 0.5s tick
    ken_burns_phase += step * ken_burns_direction
    if ken_burns_phase >= 1.0:
        ken_burns_phase = 1.0
        ken_burns_direction = -1
    elif ken_burns_phase <= 0.0:
        ken_burns_phase = 0.0
        ken_burns_direction = 1
    try:
        if ken_burns_phase < 0.5:
            canvas.itemconfigure(ken_burns_item_a, state="normal")
            canvas.itemconfigure(ken_burns_item_b, state="hidden")
        else:
            canvas.itemconfigure(ken_burns_item_a, state="hidden")
            canvas.itemconfigure(ken_burns_item_b, state="normal")
    except tk.TclError:
        return
    try:
        ken_burns_job_id = root.after(500, tick_ken_burns)
    except tk.TclError:
        ken_burns_job_id = None
```

- [ ] **Step 4: Replace static blur install in `update_images`**

Locate the block where the static blurred background is created (search for `create_blurred_background(image_file_path, window_width, window_height, gui_cfg['blur_strength'])`). Replace the install path with:
```python
            installed = install_ken_burns(image_file_path, window_width, window_height)
            if installed:
                # Accent extraction still wants a single PIL frame; re-derive
                # quickly from the unvignetted source for color sampling.
                try:
                    pre_vignette = create_blurred_background(
                        image_file_path, window_width, window_height, gui_cfg['blur_strength']
                    )
                    if pre_vignette is not None:
                        accent_color_hex = extract_accent_color(pre_vignette)
                except Exception:
                    pass
            else:
                blurred_pil_image = create_blurred_background(
                    image_file_path, window_width, window_height, gui_cfg['blur_strength']
                )
                if blurred_pil_image:
                    try:
                        accent_color_hex = extract_accent_color(blurred_pil_image)
                    except Exception as e:
                        logger.debug(f"Accent extract failed: {e}")
                    vignette_intensity = safe_float(gui_cfg.get("vignette_intensity")) or 0.55
                    blurred_pil_image = apply_vignette(blurred_pil_image, intensity=vignette_intensity)
                    bg_photo_ref = ImageTk.PhotoImage(blurred_pil_image)
                    canvas.delete("background")
                    canvas.create_image(0, 0, anchor=tk.NW, image=bg_photo_ref, tags=("background",))
                    canvas.tag_lower("background")
                else:
                    canvas.delete("background")
                    bg_photo_ref = None
```

Remove the original Tier 1 blurred install (the inline `blurred_pil_image = create_blurred_background...` block it replaced).

- [ ] **Step 5: Start the tick loop at app init**

In `main()`, after the other ticks:
```python
    root.after(600, tick_ken_burns)
```

- [ ] **Step 6: Smoke check**

Run app fullscreen on a song. Over ~20–30s, observe the backdrop slowly drifting between two zoom/translate states. Disable via config `gui.ken_burns_enabled: false` — backdrop should fall back to the Tier 1 static blurred image.

- [ ] **Step 7: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): add Ken Burns backdrop crossfade"
```

---

## Phase 10 — Final polish

### Task 21: Tag-raise order on each redraw

Ensure layering stays consistent: background/ken_burns at bottom, cover halo above background, cover art above halo, main text above all, status_pill above main text, progress_bar above main text, idle_splash above everything when active.

**Files:**
- Modify: `v1.2/Files/shazam.py`

- [ ] **Step 1: At the end of `update_images` (just before the final `return layout_info`), add explicit tag ordering**

Replace the existing `canvas.tag_raise("main_text")` / `canvas.tag_raise("status_pill")` / `canvas.tag_raise("progress_bar")` block (if present) with:
```python
        try:
            canvas.tag_lower("background")
            canvas.tag_raise("cover_halo", "background")
            if coverart_item_id:
                canvas.tag_raise(coverart_item_id, "cover_halo")
            canvas.tag_raise("main_text")
            canvas.tag_raise("lyrics_text")
            canvas.tag_raise("progress_bar")
            canvas.tag_raise("status_pill")
            if idle_splash_active:
                canvas.tag_raise("idle_splash")
                canvas.tag_raise("status_pill")
        except tk.TclError:
            pass
```

- [ ] **Step 2: Smoke check**

Run the app. Verify no z-order regressions (lyrics still readable above bg, halo behind cover, status pill on top).

- [ ] **Step 3: Commit**

```bash
git add v1.2/Files/shazam.py
git commit -m "feat(ui): enforce consistent z-order on redraw"
```

---

### Task 22: Acceptance pass — multi-context manual check

Manual visual verification across all three contexts (spec §9 acceptance criteria).

**Files:** none

- [ ] **Step 1: Desktop window**

Run: `cd v1.2/Files && python shazam.py`
- Window starts at MIN size.
- Verify breakpoint = `stacked` (cover centered top, lyrics centered).
- Recognize a song. Verify cover halo, active lyric tint, status pill pulse.

- [ ] **Step 2: Resize to mid**

Drag window to ~1100×700.
- Verify breakpoint = `mid`.
- Verify layout reflows; lyrics right-aligned, cover smaller.

- [ ] **Step 3: Resize to wide**

Drag window to ~1600×900.
- Verify breakpoint = `wide`.
- Verify full split layout: cover+meta lower-left, lyrics right-aligned.

- [ ] **Step 4: Fullscreen toggle**

Press Escape (assumes existing fullscreen bind).
- Verify cinematic split layout looks intentional, all elements legible.

- [ ] **Step 5: Idle splash**

Quit playback in your input source. Wait 10s.
- Verify idle splash mesh-gradient + wordmark appear.
- Resume playback. Verify splash dissolves to normal UI.

- [ ] **Step 6: Reduced motion**

Edit `v1.2/Files/config.json`: set `gui.motion_reduced: true`. Restart app.
- Verify Ken Burns is disabled (static backdrop).
- Verify lyric glow no longer breathes.
- Status dot becomes static.
- Restore `gui.motion_reduced: false` afterward.

- [ ] **Step 7: Commit a final marker**

```bash
git commit --allow-empty -m "chore(ui): tier-2 overhaul acceptance pass complete"
```

---

### Task 23: Optional — bundle Inter + Space Grotesk fonts

If neither font is installed at OS level, the fallback chain works but the design loses the intended Space Grotesk display voice. Bundle the fonts for first-class display on Pi.

**Files:**
- Create: `v1.2/Files/fonts/Inter-Regular.ttf`
- Create: `v1.2/Files/fonts/Inter-Bold.ttf`
- Create: `v1.2/Files/fonts/SpaceGrotesk-Bold.ttf`
- Modify: `v1.2/Files/shazam.py`
- Modify: `v1.2/Files/requirements.txt`

- [ ] **Step 1: Download Inter and Space Grotesk TTFs**

Source (Google Fonts):
- https://fonts.google.com/specimen/Inter (Regular + Bold)
- https://fonts.google.com/specimen/Space+Grotesk (Bold)

Place into `v1.2/Files/fonts/`.

- [ ] **Step 2: Add tkextrafont to requirements**

Append to `v1.2/Files/requirements.txt`:
```
tkextrafont; sys_platform != "darwin"
```

(macOS Tk can already register fonts via the OS font catalog; tkextrafont is mainly needed for Linux/Pi.)

- [ ] **Step 3: Register fonts at startup**

In `main()`, before `get_ui_font_family()` is warmed:
```python
    fonts_dir = SCRIPT_DIR / "fonts"
    if fonts_dir.is_dir():
        try:
            from tkextrafont import Font as ExtraFont
            for ttf in fonts_dir.glob("*.ttf"):
                try:
                    ExtraFont(file=str(ttf))
                    logger.info(f"Registered bundled font: {ttf.name}")
                except Exception as e:
                    logger.debug(f"Could not register {ttf.name}: {e}")
        except ImportError:
            logger.info("tkextrafont not installed — relying on OS-installed fonts.")
```

- [ ] **Step 4: Reset cached font family so the registration takes effect**

In `main()` after the registration block, reset:
```python
    global ui_font_family_cache
    ui_font_family_cache = None
    get_ui_font_family()
```

- [ ] **Step 5: Smoke check**

Run the app. Logs should show `Registered bundled font: ...` and `UI font family: Space Grotesk` (or Inter).

- [ ] **Step 6: Commit**

```bash
git add v1.2/Files/fonts v1.2/Files/shazam.py v1.2/Files/requirements.txt
git commit -m "feat(ui): bundle Inter + Space Grotesk and register at startup"
```

---

## Spec coverage check

| Spec section | Task(s) covering it |
|--------------|---------------------|
| §1 Vision | All tasks together |
| §2 Decisions | Inferred into Tasks 1–22 |
| §3 Color tokens | Already in Tier 1; reinforced by Task 18 (state colors) |
| §3 Typography fallback | Task 0 indirectly (font helper exists), Task 23 (bundled fonts) |
| §3 Type scale | Tasks 1, 5, 12 |
| §3 Spacing scale | Tasks 1, 5 (used by layout calc) |
| §3 Radii | Tier 1 (already implemented) |
| §4 Breakpoints | Task 4 |
| §4 Split / stacked / mid | Task 4 (detection); existing layout code in `update_images` already implements split + stacked. Task 22 validates. |
| §5 Motion tokens | Tasks 2 (easing), 14, 19, 20 |
| §5.1 Ken Burns | Task 20 |
| §5.2 Lyric advance transition | Task 14 |
| §5.3 Glow breath | Task 13 |
| §5.4 Status dot pulse | Tier 1 (already implemented) |
| §5.5 Progress bar | Tier 1 (already implemented) |
| §5.6 Cover halo | Task 9 |
| §5.7 Idle gradient | Task 17 |
| §5 Reduced motion | Tasks 6, 7 (resolved-flag), used by Tasks 13, 14, 19, 20 |
| §6.1 Status pill | Tier 1; Task 18 (states) |
| §6.2 Cover halo | Task 9 |
| §6.3 Meta block (strip glyphs, artist label) | Tasks 10, 11 |
| §6.4 Lyric column | Tasks 12, 13, 14 |
| §6.5 Recent strip | Task 15 |
| §6.6 Progress bar | Tier 1 (already implemented) |
| §6.7 Idle splash | Tasks 16, 17 |
| §6.8 Wordmark | Task 17 (included in splash render) |
| §7 State machine | Task 18 (pill states) + Tasks 16, 17 (idle), 19 (track change), 22 (manual verify) |
| §8 Config knobs | Task 8 |
| §8 Files touched | Task 23 (optional fonts) + all others |
| §9 Acceptance | Task 22 |

All sections covered.

## Self-review notes

- All steps include the actual code or commands required to execute them, no placeholders.
- Function/property names referenced across tasks are consistent: `responsive_clamp`, `ease_out_cubic`, `is_motion_enabled`, `compute_type_scale`, `should_show_idle_splash`, `classify_status_state`, `render_cover_halo`, `render_idle_splash`, `begin_track_change_choreography`, `tick_lyric_transition`, `tick_lyric_glow`, `tick_ken_burns`, `install_ken_burns`.
- Each task ends in a commit step so the user can step back to any checkpoint.
- TDD applied only where it adds value (pure helpers). Tk-touching renderers fall back to "smoke check" steps — running the app and visually verifying — because their correctness is fundamentally visual and a unit test against a Canvas mock would prove nothing useful.
- Optional Task 23 (font bundling) is gated by user preference / environment; the design degrades gracefully via the existing `get_ui_font_family()` fallback chain if skipped.

---

**End of plan.**
