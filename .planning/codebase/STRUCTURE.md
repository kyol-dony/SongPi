# Codebase Structure

**Analysis Date:** 2026-09-28

## Directory Layout

```
SongPi/
├── v1.2/                        # ACTIVE codebase — latest maintained version
│   ├── Files/                   # Python application (the actual "src" dir)
│   │   ├── shazam.py            # Entire app: entry point + GUI + recognition + persistence
│   │   ├── led_controller.py    # LedController class (serial → Arduino)
│   │   ├── config.json          # User-editable runtime configuration
│   │   ├── requirements.txt     # Python dependencies (pip)
│   │   ├── pytest.ini           # Test runner config
│   │   ├── Run.bat               # Windows launcher (activates venv, runs shazam.py)
│   │   ├── tests/                # Pytest unit tests (pure functions only)
│   │   │   ├── conftest.py       # Adds Files/ to sys.path for `import shazam`
│   │   │   ├── test_ui_helpers.py
│   │   │   └── test_led_controller.py
│   │   ├── venv/                 # Local virtualenv (gitignored)
│   │   ├── __pycache__/          # Bytecode cache (gitignored)
│   │   ├── .pytest_cache/        # Pytest cache (gitignored)
│   │   ├── image.jpg             # Current cover art (app-generated, gitignored)
│   │   ├── last_state.json       # Last-played song (app-generated, gitignored)
│   │   ├── history_state.json    # Recent-songs snapshot (app-generated, gitignored)
│   │   └── lyrics_cache.json     # Cached lyrics lookups (app-generated, gitignored)
│   ├── Arduino/
│   │   └── SongPiLedStrip/
│   │       ├── platformio.ini    # PlatformIO project config (Arduino Uno + FastLED)
│   │       └── src/main.cpp      # LED strip firmware (serial protocol handler)
│   ├── history_images/           # Cached cover-art JPEGs for history panel (app-generated, gitignored)
│   ├── song_history.log          # Append-only text log of recognized songs (app-generated, gitignored)
│   ├── Start.bat                 # Top-level Windows launcher → Files/Run.bat
│   ├── run_macos.sh              # macOS launcher (activates Files/venv, runs shazam.py)
│   ├── setup_macos.sh            # macOS first-time venv/dependency setup
│   ├── 1st time setup.bat        # Windows first-time venv/dependency setup
│   ├── READ ME.txt               # Version-specific notes
│   └── SongPi - full Windows.zip # Packaged release artifact
├── v1.1/                         # FROZEN legacy version (previous release)
│   ├── Files/
│   │   ├── SongPi.py             # v1.1 monolith (pre-LED, pre-lyrics)
│   │   ├── config.json
│   │   └── requirements.txt
│   ├── SongPi.bat
│   └── setup.bat
├── SongPi - Pi version/          # FROZEN Raspberry Pi variant
│   ├── SongPi.py                 # Minimal 298-line variant, no LED/lyrics
│   ├── config.json
│   └── Song Pi - Pi version.zip
├── SongPi - portable Windows/    # Packaged portable-Windows release artifact
│   ├── README.txt
│   └── SongPi - portable Windows.7z
├── readme_images/                # Screenshots referenced by README.md
├── .planning/                    # GSD planning artifacts (this mapper's output lives here)
│   └── codebase/                 # ← ARCHITECTURE.md / STRUCTURE.md written here
├── docs/                         # Superpowers/GSD scratch docs (gitignored)
├── README.md                     # Project overview, setup instructions per OS
├── RELEASE_LOG.md                # Version history / changelog
└── LICENSE
```

Stray top-level `bin/`, `include/`, `lib/`, and `pyvenv.cfg` at the repo root
are leftovers of a Python virtualenv created directly in the repo root
(`pyvenv.cfg` points at Homebrew Python 3.14). They are gitignored
(`.gitignore` lines `/bin/`, `/include/`, `/lib/`, `/pyvenv.cfg`) and are not
part of the application — do not treat them as source directories.

## Directory Purposes

**`v1.2/Files/`:**
- Purpose: the entire Python application — this is the directory to work in for almost any change
- Contains: one large application module (`shazam.py`), one supporting module (`led_controller.py`), runtime config, and tests
- Key files: `shazam.py` (4,608 lines — GUI, recognition, persistence, lyrics), `led_controller.py` (152 lines — hardware I/O), `config.json` (runtime tunables), `requirements.txt` (pinned deps)

**`v1.2/Files/tests/`:**
- Purpose: unit tests for logic that doesn't require Tk, real audio hardware, or network access
- Contains: pytest test modules that stub `pyaudio`/`screeninfo`/`shazamio` before importing `shazam` (see `test_ui_helpers.py:1-15`), then call pure functions directly
- Key files: `conftest.py` (path setup), `test_ui_helpers.py` (365 lines, layout/text/easing helpers), `test_led_controller.py` (39 lines, `LedController` protocol behavior)

**`v1.2/Arduino/SongPiLedStrip/`:**
- Purpose: optional companion firmware for the physical LED strip feature
- Contains: PlatformIO project (`platformio.ini`) and a single firmware source file
- Key files: `src/main.cpp` — parses `COLOR r g b` / `STATE name` / `BRIGHTNESS n` commands sent by `led_controller.py` and drives a WS2812B strip via FastLED

**`v1.1/` and `SongPi - Pi version/`:**
- Purpose: frozen historical releases, kept for reference/rollback, not actively developed
- Contains: self-contained older copies of the app (own `SongPi.py`, own `config.json`, own launcher scripts)
- Key files: `v1.1/Files/SongPi.py` (1,763 lines), `SongPi - Pi version/SongPi.py` (298 lines, Pi-focused, no LED/lyrics support)
- Do not add new features here; port changes to `v1.2/Files/` instead.

**`SongPi - portable Windows/`:**
- Purpose: holds a packaged portable-Windows distributable (`.7z`) and its README; not source code

**`readme_images/`:**
- Purpose: screenshots embedded in the root `README.md`

**`.planning/`:**
- Purpose: GSD (this tool's) planning and codebase-mapping output; `.planning/codebase/` is where this document lives

## Key File Locations

**Entry Points:**
- `v1.2/Files/shazam.py` (`main()` at line 4526): primary application entry point
- `v1.2/Files/Run.bat`: Windows launcher that activates `venv` and runs `python shazam.py`
- `v1.2/run_macos.sh`: macOS launcher that activates `Files/venv` and runs `python3 shazam.py`
- `v1.2/Start.bat`: top-level convenience launcher that calls `Files\Run.bat`

**Configuration:**
- `v1.2/Files/config.json`: all runtime tunables (`audio`, `recognition`, `gui`, `network`, `led`, `lyrics`, `logging` sections)
- `v1.2/Files/shazam.py::load_config()` (line 170): in-code default config, deep-merged with `config.json`
- `v1.2/Arduino/SongPiLedStrip/platformio.ini`: firmware build config (board, framework, libs)
- `v1.2/Arduino/SongPiLedStrip/src/main.cpp` (top of file): `DATA_PIN`, `LED_COUNT`, `MAX_POWER_MILLIAMPS` — must stay aligned with `config.json`'s `led` section per the code comment

**Core Logic:**
- `v1.2/Files/shazam.py`: everything — audio capture, Shazam recognition, GUI rendering, history/state persistence, lyrics sync
- `v1.2/Files/led_controller.py`: `LedController` class, the only class-based abstraction in the app

**Testing:**
- `v1.2/Files/tests/`: all tests; run with `pytest` from `v1.2/Files/` (uses `pytest.ini`, `testpaths = tests`)

## Naming Conventions

**Files:**
- Application module: lowercase, matches its domain (`shazam.py`, `led_controller.py`)
- Test files: `test_<subject>.py` (e.g., `test_led_controller.py`, `test_ui_helpers.py`), matching `pytest.ini`'s `python_files = test_*.py`
- Generated/state JSON files: `snake_case` matching their content (`last_state.json`, `history_state.json`, `lyrics_cache.json`)
- Version directories use literal version labels (`v1.1`, `v1.2`) or descriptive platform names (`SongPi - Pi version`, `SongPi - portable Windows`) rather than a uniform scheme

**Directories:**
- `Files/` (capitalized) holds the actual Python source per version — a naming holdover from the packaged-release layout (this is also the directory a packaged `.zip`/`.7z` extracts into)
- `history_images/` and `readme_images/`: plural, `snake_case`, purpose-named

**Code (within `shazam.py`):**
- Functions: `snake_case`, verb-first (`record_audio`, `update_images`, `process_recognition_result`)
- Module-level globals: `snake_case`, declared with type hints near the top of the file (e.g., `accent_color_hex: str = "#7c8fff"`) and mutated via `global` inside functions
- Constants: `UPPER_SNAKE_CASE` (`SCRIPT_DIR`, `CONFIG_FILENAME`, `MIN_WINDOW_WIDTH`)
- Type hints used throughout (`Optional`, `Dict[str, Any]`, `Tuple`, `List`, `Literal`, `Union` from `typing`)

## Where to Add New Code

**New feature (recognition/GUI/persistence logic):**
- Primary code: add a new top-level function to `v1.2/Files/shazam.py`, grouped near related existing functions (the file is organized into informal sections separated by `# --- Section Name ---` comments, e.g. `# --- Configuration Loading ---`, `# --- Song Recognition ---`, `# --- Main Execution ---`)
- Tests: add to `v1.2/Files/tests/test_ui_helpers.py` if the function is pure (no Tk/audio/network), following the existing pattern of stubbing native modules in the test file header; do not add Tk-dependent tests without also adding a way to stub `tkinter`

**New hardware/serial integration (LED-strip-like):**
- Implementation: follow the `LedController` pattern in `v1.2/Files/led_controller.py` — a small class owning only the transport, with domain logic (colors, animations) pushed to firmware rather than added to `shazam.py`
- Tests: `v1.2/Files/tests/test_led_controller.py`

**New config option:**
- Add the default to the in-code default dict inside `load_config()` (`v1.2/Files/shazam.py:170`), then read it via `config['section']['key']` where needed; also add it to `v1.2/Files/config.json` so it's visible/editable

**Firmware change:**
- `v1.2/Arduino/SongPiLedStrip/src/main.cpp`; keep `DATA_PIN`/`LED_COUNT`/protocol commands in sync with `led_controller.py`'s command strings (`"COLOR %d %d %d"`, `"STATE ..."`, `"BRIGHTNESS %d"`)

**Do not:**
- Add new code to `v1.1/` or `SongPi - Pi version/` — these are frozen; port fixes/features forward into `v1.2/Files/` instead
- Introduce a `src/` package layout without also updating `tests/conftest.py`'s `sys.path` injection and the `Run.bat`/`run_macos.sh` launchers that assume `shazam.py` lives directly in `Files/`

## Special Directories

**`v1.2/Files/venv/` and `v1.2/.venv/`:**
- Purpose: Python virtual environments (Windows-created `venv`, macOS-created via `setup_macos.sh`)
- Generated: Yes (by `1st time setup.bat` / `setup_macos.sh`)
- Committed: No (gitignored via `venv/`, `.venv/`, `.venv*/`, `*/venv/`)

**`v1.2/history_images/`:**
- Purpose: cached cover-art JPEGs backing the on-screen song-history panel, pruned by `cleanup_old_history_images()` in `shazam.py`
- Generated: Yes, at runtime as songs are recognized
- Committed: No (gitignored via `history_images/`) — note: files currently present in this directory were committed before the ignore rule was added; new files won't be tracked

**`v1.2/Files/__pycache__/`, `v1.2/Files/.pytest_cache/`:**
- Purpose: Python bytecode cache / pytest cache
- Generated: Yes
- Committed: No

**Root `bin/`, `include/`, `lib/`, `pyvenv.cfg`:**
- Purpose: accidental artifacts of a virtualenv created at the repo root (not the app's venv)
- Generated: Yes (by `python -m venv` run at repo root)
- Committed: No (explicitly gitignored) — safe to delete; not referenced by any launcher script

**`.superpowers/`, `docs/`:**
- Purpose: scratch/planning output from AI-assisted development tooling, unrelated to the application itself
- Generated: Yes
- Committed: No (gitignored)

---

*Structure analysis: 2026-09-28*
