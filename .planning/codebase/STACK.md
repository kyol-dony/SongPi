# Technology Stack

**Analysis Date:** 2026-09-28

## Repository Layout Note

This repository contains multiple generations of the same desktop application, side by side:

- **`v1.2/`** — current/active version. Cross-platform (Windows + macOS, with Linux/Pi support carried over from earlier versions). This is where active development happens (`v1.2/Files/shazam.py` was last modified 2026-09-28). All analysis below focuses on this version unless noted otherwise.
- **`v1.1/`** — previous Windows-only release, kept for reference (`v1.1/Files/SongPi.py`).
- **`SongPi - Pi version/`** — Raspberry Pi–targeted variant (`SongPi.py`), simpler feature set, no lyrics/LED integration.
- **`SongPi - portable Windows/`** — packaged portable Windows build (zipped/7z archives, not source).

There is no package manager manifest at the repo root (no root `requirements.txt`/`pyproject.toml`); each version directory is self-contained with its own `requirements.txt` and virtual environment.

## Languages

**Primary:**
- Python 3 — application logic, entire app (`v1.2/Files/shazam.py`, `v1.2/Files/led_controller.py`)

**Secondary:**
- C++ (Arduino/AVR framework) — LED strip firmware, `v1.2/Arduino/SongPiLedStrip/src/main.cpp`
- Batch script (Windows `.bat`) — setup/launch scripts, `v1.2/1st time setup.bat`, `v1.2/Start.bat`, `v1.2/Files/Run.bat`
- Bash — macOS setup/launch scripts, `v1.2/setup_macos.sh`, `v1.2/run_macos.sh`

## Runtime

**Environment:**
- Python 3.12 required for `v1.2` (enforced by `v1.2/setup_macos.sh`, which checks `sys.version_info` and refuses to proceed on any version other than 3.12). This is because `shazamio==0.7.0` and `numpy==2.1.2` pin to Python 3.12 wheels.
- Older variants (`v1.1`, `SongPi - Pi version`) recommend Python 3.8+ (per `README.md`).
- A stray repo-root venv (`pyvenv.cfg`, `bin/`, `lib/`, `include/`) is built against Python 3.14 — this is a local dev artifact, not a supported runtime for the app; `v1.2`'s own venv (`v1.2/Files/venv/pyvenv.cfg`) correctly targets 3.12.13.
- audioop (removed from stdlib in Python 3.13+) is restored via `audioop-lts` for `pydub` compatibility — see `v1.2/Files/requirements.txt`.

**Package Manager:**
- pip (no lockfile beyond pinned versions in `requirements.txt`; no `Pipfile.lock`/`poetry.lock`)
- Virtual environments are created per-platform via `python -m venv` (Windows: `1st time setup.bat`; macOS: `setup_macos.sh`)

## Frameworks / GUI

**Core:**
- Tkinter (stdlib) — the entire GUI: fullscreen/windowed album-art display, history panel, lyrics overlay (`v1.2/Files/shazam.py`, uses `tkinter as tk`, `tkinter.font`)
- `asyncio` — drives the recognition loop (`async def recognize_song`, `async def main_loop` equivalent in `v1.2/Files/shazam.py:4343`)
- `threading` — background recognition thread separate from the Tk main loop; also used for LED serial writes (`v1.2/Files/led_controller.py`)

**Testing:**
- pytest — `v1.2/Files/pytest.ini` (testpaths = `tests`, filters `DeprecationWarning`)
- Test suite: `v1.2/Files/tests/test_ui_helpers.py`, `v1.2/Files/tests/test_led_controller.py`, with shared fixtures in `v1.2/Files/tests/conftest.py`
- Tests stub out native-dependent modules (`pyaudio`, `screeninfo`, `shazamio`) via `sys.modules` injection so `shazam.py` can be imported and its pure helper functions unit-tested without hardware/network (see `v1.2/Files/tests/test_ui_helpers.py:1-14`)

**Build/Dev:**
- PlatformIO — builds the Arduino LED firmware (`v1.2/Arduino/SongPiLedStrip/platformio.ini`, env `uno`, `platform = atmelavr`, `framework = arduino`)
- FastLED library (`lib_deps = fastled/FastLED`) for the Arduino sketch

## Key Dependencies

(from `v1.2/Files/requirements.txt`)

**Critical:**
- `shazamio==0.7.0` — Shazam song-recognition client (pinned to the pure-Python build to avoid native-core segfaults on macOS)
- `pyaudio` — microphone/audio-input capture
- `numpy==2.1.2` — pinned because `shazamio` 0.7.0 depends on it; wheel availability constrains the app to Python 3.12
- `pillow` — image processing (cover art blur, resize, color sampling, halo/vignette effects)
- `requests` — HTTP client for lyrics APIs and cover-art image downloads
- `screeninfo` — multi-monitor detection for window placement/fullscreen sizing
- `pyserial>=3.5` — serial communication with the Arduino LED controller
- `audioop-lts` (conditional: `python_version >= "3.13"`) — restores removed stdlib `audioop` module for `pydub`

**Infrastructure/stdlib-heavy:**
- `tkinter`, `asyncio`, `threading`, `logging`, `json`, `pathlib`, `tempfile`, `shutil`, `colorsys`, `unicodedata` — all stdlib, used extensively throughout `v1.2/Files/shazam.py`

## Configuration

**Environment:**
- No `.env` file usage detected; all runtime configuration is via `v1.2/Files/config.json` (JSON, loaded at startup)
- Config sections: `audio`, `recognition`, `gui`, `network`, `led`, `lyrics`, `logging` — see `v1.2/Files/config.json` for full schema (sample rate, chunk size, retry/timeout tuning, GUI layout ratios, LED serial port/baud/brightness, lyrics provider toggles, log level/format)
- No secrets/API keys required — all external services used (LRCLIB, NetEase mirror, Shazam via `shazamio`) are keyless public endpoints

**Build:**
- No bundler/transpiler; this is a plain-Python script app, launched directly (`python shazam.py`)
- Arduino firmware build config: `v1.2/Arduino/SongPiLedStrip/platformio.ini`

## Platform Requirements

**Development:**
- macOS: Python 3.12 (Homebrew `python@3.12` or python.org 3.12 pkg), `portaudio` (via `brew install portaudio`) for PyAudio's native build
- Windows: Python 3.8+ on PATH; `Setup.bat`/`1st time setup.bat` bootstraps the venv
- Linux/Raspberry Pi: Python 3.8+, ALSA audio stack (app sets `PA_ALSA_PLUGHW=1` on Linux only, `v1.2/Files/shazam.py:29-30`)

**Production:**
- Runs as a local desktop/kiosk app — no server deployment; distributed as a portable folder (`SongPi - full Windows.zip`) or run from source
- Optional hardware: Arduino Uno + addressable LED strip over USB serial for ambient lighting reactive to album art color

---

*Stack analysis: 2026-09-28*
