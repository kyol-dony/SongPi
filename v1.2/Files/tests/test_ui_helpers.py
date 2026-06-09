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
