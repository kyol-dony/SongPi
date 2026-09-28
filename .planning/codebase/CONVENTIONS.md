# Coding Conventions

**Analysis Date:** 2026-09-28

## Scope Note

SongPi is a Python desktop app (Tkinter GUI + audio recognition). The active, maintained codebase is `v1.2/Files/` (`shazam.py`, `led_controller.py`). Older top-level directories (`SongPi - Pi version/`, `v1.1/`) contain legacy/parallel copies and are not the convention source of truth — do not mirror their patterns in new work. There is no JS/TS, no linter config (no `.flake8`, `pyproject.toml`, `.pylintrc`, or `mypy.ini`), and no formatter config — style is enforced by convention only, not tooling.

## Naming Patterns

**Files:**
- `snake_case.py` for all modules: `shazam.py`, `led_controller.py`.
- Test files mirror the module under test: `test_led_controller.py` tests `led_controller.py`, `test_ui_helpers.py` tests pure-function helpers inside `shazam.py`.

**Functions:**
- `snake_case`, verb-first, descriptive: `load_config`, `record_audio`, `extract_dominant_color`, `should_use_cinematic_mode`, `classify_status_state` (`v1.2/Files/shazam.py`).
- Predicate functions that return `bool` are prefixed `is_`/`has_`/`should_`: `is_low_power_host`, `has_recent_track`, `should_show_idle_splash` (`v1.2/Files/shazam.py:1132,1161,1148`).
- Private/internal helpers are prefixed with a single underscore: `_lyrics_http_get`, `_connect`, `_write_now`, `_close_unlocked` (`v1.2/Files/led_controller.py`, `v1.2/Files/shazam.py:1991`).
- Tkinter event handlers/animation "tick" callbacks use a `tick_`/`render_`/`on_` naming scheme: `tick_ken_burns`, `tick_status_pulse`, `render_cover_halo`, `on_resize`, `on_closing`.

**Variables:**
- `snake_case` throughout, no Hungarian notation.
- Module-level mutable state is declared at file top under a `# --- Global State ---` banner with explicit type annotations, e.g. `config: Dict[str, Any] = {}`, `led_controller: Optional[LedController] = None` (`v1.2/Files/shazam.py:64-156`).
- Job-id/thread-id tracking variables use a `_job_id` / `_thread` suffix: `status_pulse_job_id`, `resize_job_id`, `recognition_thread`.
- Constants are `UPPER_SNAKE_CASE` and grouped under `# --- Constants ---`: `CONFIG_FILENAME`, `MIN_WINDOW_WIDTH`, `SCRIPT_DIR` (`v1.2/Files/shazam.py:34-62`).

**Types:**
- No custom classes for data — plain `Dict[str, Any]` structures are used for config, lyrics state, track-change state, etc., always with a `typing` annotation at the declaration site.
- The one class in the reference module, `LedController` (`v1.2/Files/led_controller.py:27`), is `PascalCase`; its public API is a small set of verbs (`set_track_color`, `set_state`, `close`) and private methods are underscore-prefixed.

## Code Style

**Formatting:**
- No formatter (no Black/Ruff config). 4-space indentation, no semicolons, double-quoted strings preferred for prose/messages, single quotes appear interchangeably for dict keys (`config['audio']` vs `config.get("gui", {})`) — follow whichever style is local to the function you're editing.
- Line length is not machine-enforced; existing code generally stays under ~110 characters but multi-arg function signatures are wrapped across lines when long, e.g. `record_audio(record_seconds_override: Optional[float] = None) -> Tuple[Optional[str], Optional[float]]:` (`v1.2/Files/shazam.py:350`).

**Linting:**
- None configured. Rely on `pytest` runs and manual review as the correctness gate.

**File header/footer banners:**
- `shazam.py` opens with `# --- START OF FILE shazam.py ---` and closes with `# --- END OF FILE shazam.py ---` (`v1.2/Files/shazam.py:1,4608`). Preserve this convention if the file is ever regenerated wholesale.

**Section banners:**
- Large modules are divided into named sections with `# --- Section Name ---` comments, e.g. `# --- Constants ---`, `# --- Audio Handling ---`, `# --- Lyrics Handling ---`, `# --- GUI Update Helpers ---`, `# --- Main Execution ---` (`v1.2/Files/shazam.py`, grep `^# ---`). When adding a new logical group of functions, add a matching banner rather than interleaving unrelated concerns.

## Import Organization

**Order (as seen in `v1.2/Files/shazam.py:1-28`):**
1. Third-party/stdlib mixed together, roughly grouped by purpose (audio: `pyaudio`, `wave`; async: `asyncio`; UI: `tkinter as tk`, `tkinter.font as tkFont`; recognition: `shazamio.Shazam`; HTTP: `requests`; imaging: `PIL`).
2. Stdlib utility imports follow (`io`, `os`, `json`, `math`, `colorsys`, `re`, `unicodedata`, `threading`, `logging`, `tempfile`, `datetime`, `shutil`, `sys`, `time`).
3. `typing` imports as one line: `from typing import Optional, Dict, Any, Tuple, List, Literal, Union`.
4. `pathlib.Path`.
5. Local module import last: `from led_controller import LedController`.

There are no path aliases (flat two-file module layout). New local modules should be imported by bare module name (the `tests/conftest.py` inserts `v1.2/Files/` onto `sys.path` to make this work — see TESTING.md).

**Platform guards:** OS-specific setup is gated immediately after imports, not buried in functions: `if sys.platform.startswith("linux"): os.environ.setdefault('PA_ALSA_PLUGHW', '1')` (`v1.2/Files/shazam.py:31-32`).

## Error Handling

**Patterns:**
- Every I/O boundary (file read, audio device call, HTTP request, Tk operation) is wrapped in a specific `try/except` with the narrowest applicable exception type caught first, followed by a broad `except Exception as e:` fallback — never a bare `except:`. Example: `load_config` catches `FileNotFoundError` then `json.JSONDecodeError` (`v1.2/Files/shazam.py:243-246`); `record_audio` catches `IOError`, then `OSError`, then `Exception` at different call depths (`v1.2/Files/shazam.py:412-467`).
- Tkinter calls that can legally fail during teardown/resize (e.g. widget destroyed mid-animation) catch `tk.TclError` specifically and swallow it silently or log at debug level (`v1.2/Files/shazam.py:617,836,857,876,880`).
- Failures are logged, not raised, in most GUI/background-thread code — the app is designed to degrade gracefully (missing LED hardware, missing lyrics, no network) rather than crash. `LedController._connect` is the canonical example: on any exception it logs a warning and returns `False` rather than propagating (`v1.2/Files/led_controller.py:63-66`).
- Pure validation helpers (e.g. `hex_to_rgb`) `raise ValueError` with a descriptive message instead of returning a sentinel, and are the only functions tested for `pytest.raises` (`v1.2/Files/led_controller.py:18-24`; `v1.2/Files/tests/test_led_controller.py:9-12`).
- The top-level `main()` wraps `root.mainloop()` in `try/except KeyboardInterrupt` (clean shutdown via `on_closing()`) and `except Exception` with `logger.exception(...)` to capture the traceback before shutting down (`v1.2/Files/shazam.py`, end of file).

**Do this when adding new code:** catch the narrowest exception you can identify from the underlying library (IOError/OSError/json.JSONDecodeError/tk.TclError/etc.), log at an appropriate level (`debug` for expected/benign, `warning` for degraded-but-recoverable, `error`/`exception` for unexpected), and return a safe default (`None`, `False`, `{}`) instead of letting the exception bubble into the Tk main loop.

## Logging

**Framework:** stdlib `logging`, single named logger `logger = logging.getLogger("SongRecognizer")` (`v1.2/Files/shazam.py:143`, `v1.2/Files/led_controller.py:14`) shared across modules — do not create a per-module logger name.

**Patterns:**
- f-strings inside log calls are standard: `logger.warning(f"LED controller unavailable on %s: %s", ...)` — note mixed style exists (some calls use f-strings, some use `%s` placeholders, e.g. `led_controller.py:58` uses `%s`/`%d` placeholders while `shazam.py` almost exclusively uses f-strings). Prefer f-strings for new `shazam.py` code to match the dominant local style (229 f-string call sites vs 1 `.format()` call in the file).
- Level usage convention: `debug` for verbose per-call tracing (device enumeration, file paths), `info` for lifecycle/state-transition events (recognized track, thread start/stop, config loaded), `warning` for recoverable failures (device invalid, LED unavailable, retry triggered), `error` for failures that abort the current operation, `exception`/`error(..., exc_info=True)` for unexpected exceptions where the traceback is useful (`v1.2/Files/shazam.py:294,4608`-area `main()`).
- Log configuration (level, format) is derived from `config.json`'s `logging` section inside `load_config()` (`v1.2/Files/shazam.py:251,259-262`) — logging is configurable per-deployment, not hardcoded.

## Comments

**When to Comment:**
- Module/section banners (see Code Style) organize the file; inline comments are reserved for non-obvious "why" explanations, especially around hardware quirks and timing hacks. Example: the block explaining why LED serial writes must be deferred after `DTR` reset in `LedController.__init__` (`v1.2/Files/led_controller.py:35-37`), and the docstring in `record_audio` explaining why `record_start_monotonic` is returned separately (`v1.2/Files/shazam.py:351-356`).
- Comments explain platform/hardware caveats (`# Only set ALSA hint on Linux...`, `# audioop was removed in Python 3.13+...` in `requirements.txt`) rather than restating what the code does.

**Docstrings:**
- Triple-quoted `"""..."""` docstrings on most non-trivial functions, one-line summary followed by a blank line and further explanation where the "why" isn't obvious from the signature. Module-level docstring at the top of `led_controller.py` explains the design boundary ("controller owns only the transport... lighting behaviours stay on the microcontroller") — use this pattern when adding a new module: state the responsibility boundary up front.
- Simple/self-explanatory helpers (e.g. `rgb_to_hex`, `mix_rgb`) may skip docstrings when the signature and body are unambiguous — docstrings are not mandatory boilerplate, they're used where they add information.

## Function Design

**Size:** Functions are generally single-purpose and 10-60 lines; a handful of GUI layout/orchestration functions (e.g. lyrics rendering, redraw triggers) run longer because they coordinate many Tk canvas items — when extending these, prefer extracting a new pure helper function (testable without Tk, see TESTING.md) over growing the existing function further.

**Parameters:**
- Full type hints on every parameter and return value are the norm (`from typing import Optional, Dict, Any, Tuple, List, Literal, Union` imported for this purpose). New functions should be fully annotated to match.
- Config-derived values are passed explicitly as parameters into pure/testable functions rather than read from the global `config` inside them, wherever testability matters — e.g. `should_use_cinematic_mode(width, height, is_fullscreen, cfg)` and `is_motion_enabled(cfg)` take `cfg` as an argument instead of reading the module-global `config` (`v1.2/Files/shazam.py:1100,1141`). This is what makes them unit-testable in `tests/test_ui_helpers.py` without a running Tk root — follow this pattern for new logic that needs test coverage.
- Optional/nullable parameters use `Optional[X] = None` with an explicit default, never mutable default arguments.

**Return Values:**
- Functions that can fail return `Optional[T]` or a `bool` success flag rather than raising, except for pure validators (see Error Handling). Tuple returns are used for paired results, e.g. `record_audio -> Tuple[Optional[str], Optional[float]]`.

## Module Design

**Exports:**
- No `__all__` lists; both modules are imported either wholesale (`import shazam` in tests) or via explicit named imports (`from led_controller import LedController, hex_to_rgb`).

**Module boundaries:**
- `led_controller.py` is deliberately decoupled from `shazam.py`: it owns only the serial transport and line protocol, has zero Tkinter/audio dependencies, and is importable standalone (used directly in `tests/test_led_controller.py` with no stubbing required). When adding new hardware/IO integrations, follow this pattern — put them in their own module with no GUI dependency so they stay independently testable.
- `shazam.py` is a large single-file application module (4608 lines) combining audio capture, recognition, lyrics fetching, image processing, and the full Tkinter GUI. There is no package structure (`v1.2/Files/` is not a Python package — no `__init__.py` at that level; only `tests/` has one). New pure-logic helpers should still go in `shazam.py` near their related section banner rather than being split into ad hoc new files, unless the new concern is hardware/IO-bound like `led_controller.py`, in which case give it its own top-level module in `v1.2/Files/`.

---

*Convention analysis: 2026-09-28*
