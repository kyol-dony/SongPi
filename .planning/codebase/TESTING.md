# Testing Patterns

**Analysis Date:** 2026-09-28

## Scope Note

Tests live under `v1.2/Files/tests/` and exercise the active `v1.2/Files/shazam.py` and `v1.2/Files/led_controller.py` modules only. There are no tests for the legacy `SongPi - Pi version/` or `v1.1/` copies, and none should be added there — treat `v1.2/Files/` as the sole testable surface.

## Test Framework

**Runner:**
- `pytest` (version-agnostic in config; local venv shows pytest 9.x cache artifacts). Config file: `v1.2/Files/pytest.ini`.

**Config (`v1.2/Files/pytest.ini`):**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
filterwarnings =
    ignore::DeprecationWarning
```

**Assertion Library:**
- Plain `assert` statements (pytest's assertion rewriting). No `unittest.TestCase`-style assertions, no third-party assertion libraries.

**Run Commands:**
```bash
cd "v1.2/Files"
pytest                      # Run all tests (uses pytest.ini, testpaths=tests)
pytest -k hex_to_rgb        # Run tests matching a substring
pytest -v                   # Verbose per-test output
pytest tests/test_led_controller.py   # Run one file
```
There is no configured coverage tool, no `tox.ini`, and no CI workflow file found in the repo (`find . -iname "*.yml" -path "*workflows*"` returns nothing) — tests are run manually/locally only.

## Test File Organization

**Location:**
- Dedicated `tests/` directory sibling to the source modules: `v1.2/Files/tests/`, not co-located with source files.

**Naming:**
- One test file per source module, `test_<module>.py`: `tests/test_led_controller.py` ↔ `led_controller.py`; `tests/test_ui_helpers.py` covers pure helper functions defined inside `shazam.py` (no `test_shazam.py` — the name reflects the *kind* of function tested, not a 1:1 module mirror, since `shazam.py` mixes GUI code with pure helpers).

**Structure:**
```
v1.2/Files/
├── tests/
│   ├── __init__.py        # empty; makes tests/ a package
│   ├── conftest.py        # sys.path bootstrap so `import shazam` / `import led_controller` work
│   ├── test_led_controller.py
│   └── test_ui_helpers.py
├── led_controller.py
├── shazam.py
└── pytest.ini
```

## Test Structure

**Suite organization — flat functions, no test classes:**
```python
# v1.2/Files/tests/test_led_controller.py
from led_controller import LedController, hex_to_rgb


def test_hex_to_rgb_accepts_hash_or_plain_hex():
    assert hex_to_rgb("#7c8fff") == (124, 143, 255)
    assert hex_to_rgb("ff8000") == (255, 128, 0)


def test_hex_to_rgb_rejects_invalid_values():
    import pytest
    with pytest.raises(ValueError):
        hex_to_rgb("blue")
```
Every test is a standalone module-level `def test_*():` function — no `class Test...` grouping, no `setUp`/`tearDown`. Related tests are grouped by contiguous placement and a shared name prefix (e.g. all `test_breakpoint_*`, all `test_status_state_*`) rather than by class.

**Naming convention for test functions:** `test_<subject>_<expected_behavior>`, phrased as an assertion of behavior, e.g. `test_controller_clamps_brightness`, `test_extract_dominant_color_skips_black_for_next_most_used_color`, `test_should_not_show_idle_splash_when_disabled`. Names are long and descriptive by design — favor clarity over brevity when adding new tests.

**Setup pattern:** No fixtures for simple cases — objects are constructed inline at the top of the test body (`controller = LedController()`). `conftest.py` is used only for the one cross-cutting concern (import path), not for shared test fixtures/factories.

**Assertion pattern:** Single or a few direct `assert <expr> == <expected>` / `assert <expr> is True|False` lines per test; no helper assertion wrappers.

## Mocking

**Framework:** `unittest.mock` (`patch`, `patch.object`) plus pytest's built-in `monkeypatch` fixture. Both are used depending on what's being replaced.

**Patterns:**

Stubbing unimportable native/hardware modules at import time, before importing the module under test (`v1.2/Files/tests/test_ui_helpers.py:7-16`):
```python
import sys
import types

for mod_name in ("pyaudio", "screeninfo", "shazamio"):
    sys.modules.setdefault(mod_name, types.ModuleType(mod_name))
sys.modules["pyaudio"].PyAudio = type("PyAudio", (), {})
sys.modules["pyaudio"].paInt16 = 8
sys.modules["pyaudio"].paInputOverflowed = -9981
sys.modules["screeninfo"].get_monitors = lambda: []
sys.modules["shazamio"].Shazam = type("Shazam", (), {})

shazam = importlib.import_module("shazam")
```
This lets `shazam.py` (which has hard `import pyaudio` / `import screeninfo` / `from shazamio import Shazam` at module scope) be imported in a test environment without those native/network dependencies installed or reachable — required because `shazam.py` mixes pure logic and hardware imports in one file.

`monkeypatch.setattr` for replacing module-level globals and swapping in a fake Tk canvas (`v1.2/Files/tests/test_ui_helpers.py:110-132`):
```python
def test_cover_halo_uses_its_own_canvas_tag(monkeypatch):
    class FakeCanvas:
        def __init__(self):
            self.created_tags = None
        def create_image(self, *args, **kwargs):
            self.created_tags = kwargs.get("tags")
            return 42
        def tag_raise(self, *args):
            pass

    fake_canvas = FakeCanvas()
    monkeypatch.setattr(shazam, "canvas", fake_canvas)
    monkeypatch.setattr(shazam, "cover_halo_item_id", None)
    monkeypatch.setattr(shazam, "config", {"gui": {"accent_halo_intensity": 0.35}})
    monkeypatch.setattr(shazam, "build_cover_halo", lambda *args: object())
    monkeypatch.setattr(shazam.ImageTk, "PhotoImage", lambda image: object())

    shazam.render_cover_halo(100, 100, 80)

    assert fake_canvas.created_tags == ("cover_halo",)
```

`unittest.mock.patch` (context manager form) for stdlib/platform calls (`v1.2/Files/tests/test_ui_helpers.py:187-196`):
```python
from unittest.mock import patch

def test_low_power_true_for_armv7():
    with patch("platform.machine", return_value="armv7l"), \
         patch("os.cpu_count", return_value=4):
        assert shazam.is_low_power_host() is True
```

`patch.object` for mocking a same-module function dependency (`v1.2/Files/tests/test_ui_helpers.py:205-208`):
```python
def test_motion_enabled_when_config_false_and_high_power():
    cfg = {"gui": {"motion_reduced": False}}
    with patch.object(shazam, "is_low_power_host", return_value=False):
        assert shazam.is_motion_enabled(cfg) is True
```

Minimal hand-written fake/stand-in classes instead of `MagicMock` when behavior needs to be realistic, e.g. `_FakeFont` standing in for `tkFont.Font.measure` (`v1.2/Files/tests/test_ui_helpers.py:327-333`):
```python
class _FakeFont:
    """Minimal stand-in for tkFont.Font.measure that doesn't need a Tk root."""
    def __init__(self, char_px: int = 8):
        self.char_px = char_px
    def measure(self, text: str) -> int:
        return len(text) * self.char_px
```

**What to Mock:**
- Native/hardware modules that can't run in a test environment (`pyaudio`, `screeninfo`, `shazamio`) — stubbed once at file top via `sys.modules`.
- Tkinter objects (`canvas`, `ImageTk.PhotoImage`) and Tk-dependent globals when testing GUI-adjacent pure logic — replaced with fakes/lambdas via `monkeypatch`, never a real `tk.Tk()` instance (no test creates a real Tk root; this keeps tests headless/CI-safe).
- Platform/environment queries (`platform.machine`, `os.cpu_count`) — mocked via `unittest.mock.patch` so tests are deterministic across dev machines.
- Same-module function dependencies, when a test wants to isolate one function's branch logic from a collaborator it calls (`is_motion_enabled` isolated from the real `is_low_power_host`) — via `patch.object`.

**What NOT to Mock:**
- Pure functions with no I/O (`hex_to_rgb`, `ease_out_cubic`, `dim_hex`, `responsive_clamp`, `format_artist_label`) are called directly with real inputs — no mocking needed or used.
- Real `PIL.Image`/`ImageDraw` objects are constructed directly (not mocked) when testing image-analysis helpers like `extract_dominant_color`, because PIL is a pure-Python-installable dependency with no hardware/network requirement — see Fixtures below.
- `LedController` in `test_led_controller.py` is exercised as a real object with `enabled: False` or an unopened `port` so it never attempts a real serial connection — no mock needed because the class's own `is_configured` guard makes it a no-op safely.

## Fixtures and Factories

**No `conftest.py` fixtures beyond the import-path bootstrap.** Test data is built ad hoc with small local helper functions defined directly in the test file, not in a separate fixtures module:
```python
# v1.2/Files/tests/test_ui_helpers.py:84-88
def _solid_with_patch(bg_rgb, patch_rgb, patch_box=(90, 90, 110, 110), size=(200, 200)):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, bg_rgb)
    ImageDraw.Draw(img).rectangle(patch_box, fill=patch_rgb)
    return img
```
Use this pattern for new tests: prefix private test-data builders with `_` and keep them next to the tests that use them unless the same builder is needed across multiple test files (none currently are — if that need arises, promote it into `conftest.py`).

**Location:** `v1.2/Files/tests/conftest.py` currently contains only the `sys.path` bootstrap:
```python
"""Pytest config: make shazam.py importable from tests."""
import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
if str(FILES_DIR) not in sys.path:
    sys.path.insert(0, str(FILES_DIR))
```

## Coverage

**Requirements:** None enforced — no coverage tool configured, no minimum threshold, no CI gate.

**Test count (as of this analysis):** 65 test functions total — 59 in `tests/test_ui_helpers.py`, 6 in `tests/test_led_controller.py`.

**What's covered:** Pure/deterministic helper functions only — color math (`hex_to_rgb`, `dim_hex`, `tune_led_color`, `extract_dominant_color`), layout/responsive math (`responsive_clamp`, `ease_out_cubic`, `compute_type_scale`, `detect_layout_breakpoint`, `should_use_cinematic_mode`), status/text formatting (`classify_status_state`, `status_dot_color`, `format_artist_label`), text-fitting helpers (`longest_word_pixel_width`, `truncate_word_to_width`, `ensure_words_fit`), idle-splash timing logic (`should_show_idle_splash`, `has_recent_track`), and the entire `LedController` serial-protocol class.

**What's NOT covered:** Audio recording/device selection (`record_audio`, `select_input_device`, `list_audio_devices`), the Shazam recognition call (`recognize_song`), lyrics fetching/HTTP (`lrclib_get`, `netease_fallback`, `_lyrics_http_get`), history/state persistence (`save_history_state`, `load_last_state`), and all real Tkinter widget rendering/event-handling code — these depend on hardware, network, or a live Tk root and are exercised manually, not by the automated suite. When adding tests for these areas, follow the existing pattern of stubbing the hardware/network boundary (`sys.modules` stub or `unittest.mock.patch` on the specific I/O call) rather than attempting to run real hardware/network in tests.

## Test Types

**Unit Tests:**
- All existing automated tests are unit tests targeting individual pure functions or the isolated `LedController` class. This is the only test type present.

**Integration Tests:**
- None. No test spins up the full `shazam.py` application flow (audio capture → recognition → GUI render) end-to-end.

**E2E Tests:**
- Not used. No browser/UI-automation framework is present (expected, given this is a desktop Tkinter app).

## Common Patterns

**Testing pure numeric/logic functions directly:**
```python
def test_ease_out_cubic_clamps_input():
    assert shazam.ease_out_cubic(-0.5) == 0.0
    assert shazam.ease_out_cubic(2.0) == 1.0
```

**Testing config-driven branching by passing a config dict literal, not the real global config:**
```python
def test_mid_breakpoint_uses_compact_cinematic_layout():
    cfg = {"enabled": True, "force_cinematic_mode": False,
           "fullscreen_implies_cinematic_mode": True}
    assert shazam.should_use_cinematic_mode(1024, 900, False, cfg) is True
```
This is the dominant pattern for new tests: because production code was written to accept `cfg`/state as parameters rather than reading module globals internally (see CONVENTIONS.md → Function Design), tests build minimal literal dicts with only the keys the function under test reads.

**Error Testing:**
```python
def test_hex_to_rgb_rejects_invalid_values():
    import pytest
    with pytest.raises(ValueError):
        hex_to_rgb("blue")
```
(Note: `import pytest` is done locally inside this one test function rather than at file top — an inconsistency in the existing suite; prefer a top-level `import pytest` for new test files.)

**Async Testing:** Not present — no test covers `async def recognize_song(...)` (`v1.2/Files/shazam.py:485`), despite it being the one `async` function in the codebase. If adding coverage here, use `pytest.mark.asyncio` (not currently a dependency — `pytest-asyncio` would need to be added to `requirements.txt`) or wrap the call with `asyncio.run()` inside a synchronous test.

---

*Testing analysis: 2026-09-28*
