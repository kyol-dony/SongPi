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


def test_ease_out_cubic_starts_at_zero():
    assert shazam.ease_out_cubic(0.0) == 0.0


def test_ease_out_cubic_ends_at_one():
    assert shazam.ease_out_cubic(1.0) == 1.0


def test_ease_out_cubic_is_above_linear_in_middle():
    assert shazam.ease_out_cubic(0.5) > 0.5


def test_ease_out_cubic_clamps_input():
    assert shazam.ease_out_cubic(-0.5) == 0.0
    assert shazam.ease_out_cubic(2.0) == 1.0


def test_dim_hex_full_amount_returns_black():
    assert shazam.dim_hex("#ffffff", 1.0) == "#000000"


def test_dim_hex_zero_amount_unchanged():
    assert shazam.dim_hex("#ff8000", 0.0) == "#ff8000"


def test_dim_hex_half_amount():
    assert shazam.dim_hex("#ff0000", 0.5) == "#7f0000"


def test_simulate_alpha_on_dark_full_opacity_unchanged():
    assert shazam.simulate_alpha_on_dark("#ffffff", 1.0) == "#ffffff"


def test_simulate_alpha_on_dark_low_opacity_blends_to_scrim():
    result = shazam.simulate_alpha_on_dark("#ffffff", 0.0)
    assert result == "#0a0a0c"


def test_breakpoint_wide_at_1920x1080():
    assert shazam.detect_layout_breakpoint(1920, 1080) == "wide"


def test_breakpoint_stacked_at_400x800():
    assert shazam.detect_layout_breakpoint(400, 800) == "stacked"


def test_breakpoint_stacked_when_narrower_than_900():
    assert shazam.detect_layout_breakpoint(800, 1200) == "stacked"


def test_breakpoint_mid_at_1024x900():
    # width >= 900 satisfies wide-width, but aspect 1.137 < 1.2 -> mid.
    assert shazam.detect_layout_breakpoint(1024, 900) == "mid"


def test_breakpoint_handles_zero_height():
    assert shazam.detect_layout_breakpoint(800, 0) == "stacked"


def test_type_scale_at_1080_short_edge():
    scale = shazam.compute_type_scale(1080)
    assert scale["title"] == int(shazam.responsive_clamp(18, int(1080 * 0.035), 38))
    assert scale["lyric_active"] == int(shazam.responsive_clamp(22, int(1080 * 0.052), 64))
    assert scale["lyric_context"] == int(shazam.responsive_clamp(13, int(1080 * 0.025), 24))


def test_type_scale_clamps_at_small_size():
    scale = shazam.compute_type_scale(200)
    assert scale["title"] == 18
    assert scale["lyric_active"] == 22


def test_type_scale_clamps_at_large_size():
    scale = shazam.compute_type_scale(4000)
    assert scale["title"] == 38
    assert scale["lyric_active"] == 64
