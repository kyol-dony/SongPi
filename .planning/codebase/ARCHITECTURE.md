<!-- refreshed: 2026-09-28 -->
# Architecture

**Analysis Date:** 2026-09-28

## System Overview

SongPi is a single-process desktop application: a background thread continuously
records audio and calls the Shazam API, and the Tkinter main thread renders the
result. There is no client/server split and no database — persistence is a
handful of JSON/log files and cached JPEGs on disk. The **active, maintained
codebase is `v1.2/Files/`**; `v1.1/` and `SongPi - Pi version/` are frozen
legacy snapshots kept for reference/rollback (see "Multiple Version Trees"
below).

```text
┌───────────────────────────────────────────────────────────────────────┐
│                    Tkinter Main Thread (event loop)                   │
│  `v1.2/Files/shazam.py::main()` — root.mainloop()                     │
├───────────────────────────────┬───────────────────────────────────────┤
│   GUI render / layout          │   Event handlers                     │
│  `update_images()`,            │  `on_resize`, `toggle_fullscreen`,   │
│  `update_gui()`,                │  `reset_cursor_hide_timer`,          │
│  `redraw_history_display()`,    │  `on_closing`                        │
│  `render_lyrics_labels()`       │                                     │
└───────────────┬─────────────────┴───────────────────────────────────┘
                │  root.after(0, func, *args)  [schedule_gui_update]
                │  (only safe cross-thread hand-off point)
┌───────────────┴───────────────────────────────────────────────────────┐
│              Background "RecognitionThread" (daemon, own asyncio loop) │
│  `recognition_loop_runner()` → `periodic_recognition_task()`           │
├─────────────────┬─────────────────────────┬───────────────────────────┤
│  Audio capture   │   Shazam recognition    │  Result processing        │
│ `record_audio()` │  `recognize_song()`     │ `process_recognition_     │
│  (pyaudio, WAV)  │  (shazamio.Shazam)      │  result()` — image        │
│                  │                         │  download/cache, history, │
│                  │                         │  lyrics fetch             │
└─────────────────┴─────────────────────────┴───────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Local disk state (Files/ directory, flat JSON + JPEG files)           │
│  `config.json`, `last_state.json`, `history_state.json`,               │
│  `lyrics_cache.json`, `image.jpg`, `history_images/*.jpg`,             │
│  `song_history.log`                                                    │
└───────────────────────────────────────────────────────────────────────┘
                │
                ▼ (optional, best-effort)
┌───────────────────────────────────────────────────────────────────────┐
│  LED hardware side-channel                                             │
│  `led_controller.py::LedController` — USB serial → Arduino sketch      │
│  `v1.2/Arduino/SongPiLedStrip/src/main.cpp` (FastLED, WS2812B)         │
└───────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| App entry / lifecycle | Builds Tk window, wires event bindings, starts recognition thread, runs mainloop | `v1.2/Files/shazam.py::main()` (line 4526) |
| Config loading | Reads `config.json`, deep-merges over hardcoded defaults | `v1.2/Files/shazam.py::load_config()` (line 170) |
| Audio capture | Selects input device, records fixed-length WAV via PyAudio | `v1.2/Files/shazam.py::record_audio()`, `select_input_device()` |
| Recognition | Calls Shazamio, normalizes result shape | `v1.2/Files/shazam.py::recognize_song()` (line 485) |
| Recognition orchestration | Retry/backoff loop, drives the whole record→recognize→display cycle | `v1.2/Files/shazam.py::periodic_recognition_task()` (line 4342) |
| Result processing | Cover-art cache/download, history entry creation, lyrics fetch trigger | `v1.2/Files/shazam.py::process_recognition_result()` (line 4183) |
| GUI rendering | Canvas-based layout: cover art, blurred background, text, history panel, lyrics, status pill, progress bar, idle splash, Ken Burns motion | `v1.2/Files/shazam.py::update_images()`, `redraw_history_display()`, `render_lyrics_labels()`, `render_status_pill()`, `render_idle_splash()` |
| Cross-thread hand-off | Marshals background-thread results onto the Tk event loop | `v1.2/Files/shazam.py::schedule_gui_update()` (line 3021), `update_gui()` (line 3927) |
| History persistence | In-memory list + JSON snapshot + image cache cleanup | `v1.2/Files/shazam.py::add_to_history()`, `save_history_state()`, `load_history_state()`, `cleanup_old_history_images()` |
| State persistence | Last-played song restore-on-launch | `v1.2/Files/shazam.py::save_last_state()`, `load_last_state()` |
| Lyrics | LRC sync parsing, lrclib/NetEase lookups, cache, current-line computation | `v1.2/Files/shazam.py::prepare_lyrics_for_track()`, `request_lrclib_candidate()`, `netease_fallback()`, `compute_current_lyrics_lines()` |
| LED hardware control | Owns serial transport + tiny line protocol to Arduino; no lighting logic on the Python side | `v1.2/Files/led_controller.py::LedController` |
| LED firmware | Interprets `COLOR`/`STATE`/`BRIGHTNESS` commands, drives WS2812B strip, fades between colors | `v1.2/Arduino/SongPiLedStrip/src/main.cpp` |
| Tests | Pure-function unit tests (no Tk/audio dependency) for UI helpers and LED controller | `v1.2/Files/tests/test_ui_helpers.py`, `v1.2/Files/tests/test_led_controller.py` |

## Pattern Overview

**Overall:** Single monolithic script with a **two-thread producer/consumer**
pattern — one background worker thread produces recognition results, the
Tkinter main thread consumes them and renders. There are no framework layers
(no MVC, no DI container, no ORM); the whole application is procedural
functions operating on module-level global state (`v1.2/Files/shazam.py`,
~4,600 lines, ~100 top-level functions, one imported class `LedController`).

**Key Characteristics:**
- Function-per-concern, not class-per-concern — nearly everything in
  `shazam.py` is a free function that reads/writes module globals declared
  near the top of the file (line 64 onward).
- One deliberate OOP boundary: `LedController` (`v1.2/Files/led_controller.py`)
  is the only class in the app, isolating the stateful serial connection.
- Background work is async internally (the recognition thread runs its own
  `asyncio` event loop via `loop.run_until_complete(periodic_recognition_task(...))`)
  but the GUI is purely synchronous/event-driven (Tkinter's `root.after`
  scheduler), so async and sync never interleave on the same thread.
- Config-driven behavior: nearly every tunable (audio format, GUI timing,
  lyrics behavior, LED brightness) is read from `config.json` at call time
  rather than hardcoded, via `config['section']['key']` lookups scattered
  through the file.
- Best-effort optional hardware: LED support silently no-ops if disabled/
  misconfigured (`LedController.is_configured`), so the app runs fine without
  the Arduino attached.

## Layers

**Entry / lifecycle layer:**
- Purpose: process bootstrap, window creation, thread startup, shutdown
- Location: `v1.2/Files/shazam.py` (`main()`, `on_closing()`, `start_recognition_thread()`)
- Contains: Tk root setup, key bindings, `root.after` scheduling of periodic UI ticks (status pulse, lyric glow, Ken Burns)
- Depends on: GUI layer, recognition layer, config
- Used by: OS process launcher (`Run.bat` / `run_macos.sh`)

**Recognition/background layer:**
- Purpose: capture audio, call Shazam, retry on no-match, resolve cover art and lyrics
- Location: `v1.2/Files/shazam.py` (functions between `record_audio()` line 350 and `start_recognition_thread()` line 4495)
- Contains: PyAudio device I/O, `shazamio.Shazam` calls, HTTP downloads (`requests`), file cache writes
- Depends on: config, filesystem paths (constants near top of file), `led_controller` (indirectly, via status → LED state)
- Used by: entry layer (spawned as a daemon thread); communicates results to GUI layer only via `schedule_gui_update()`

**GUI/render layer:**
- Purpose: canvas layout and redraw of cover art, background blur/vignette, title/artist/album text, history panel, lyrics, status pill, progress bar, idle splash
- Location: `v1.2/Files/shazam.py` (functions between roughly line 538 `create_blurred_background()` and line 4011 `get_monitor_for_window()`)
- Contains: Pillow image processing, Tk Canvas drawing primitives, responsive layout math (breakpoints, font scaling)
- Depends on: config, filesystem (cached images), module-level "last known" state (`last_track_title`, `accent_color_hex`, etc.)
- Used by: `root.after` timers and `update_gui()` (invoked from the recognition thread via `schedule_gui_update`)

**Persistence layer:**
- Purpose: durable state across restarts and across recognition cycles
- Location: `v1.2/Files/shazam.py` (`load_config`, `load_last_state`/`save_last_state`, `load_history_state`/`save_history_state`, `load_lyrics_cache`/`save_lyrics_cache`)
- Contains: flat JSON file read/write, image copy/cleanup in `history_images/`
- Depends on: filesystem only (no database)
- Used by: recognition layer (writes) and entry/GUI layer (reads on startup)

**Hardware side-channel layer:**
- Purpose: reflect the current accent color / app status on an external LED strip, best-effort
- Location: `v1.2/Files/led_controller.py` (Python) + `v1.2/Arduino/SongPiLedStrip/src/main.cpp` (firmware)
- Contains: serial transport, tiny newline-delimited protocol (`COLOR r g b`, `STATE name`, `BRIGHTNESS n`), reconnect/backoff, DTR-reset delay handling
- Depends on: `pyserial` (imported lazily, optional dependency)
- Used by: GUI layer calls `led_controller.set_track_color()` / `set_state()` when accent color or status changes

## Data Flow

### Primary Request Path (song recognition cycle)

1. `periodic_recognition_task()` calls `record_audio()` to capture N seconds of audio to a temp WAV (`v1.2/Files/shazam.py:350`)
2. `recognize_song(wav_file_path)` sends the WAV to Shazam via `shazamio.Shazam().recognize()` (`v1.2/Files/shazam.py:485`)
3. On a match, `process_recognition_result(result, ...)` resolves cover art (history cache hit or HTTP download+verify), updates `song_history_list`, persists `last_state.json`/`history_state.json`, and kicks off lyrics lookup (`v1.2/Files/shazam.py:4183`)
4. The cycle's outcome (`update_data` dict) is marshalled to the main thread via `schedule_gui_update(update_gui, update_data)` (`v1.2/Files/shazam.py:4439`)
5. `update_gui()` decides whether the song actually changed, updates `current_status_message`, and — if needed — schedules `trigger_full_redraw()` (`v1.2/Files/shazam.py:3927`)
6. `trigger_full_redraw()` → `update_images()` recomputes layout and redraws canvas (cover, background blur, text, history, status pill), and if lyrics are enabled, `restart_lyrics_sync()` begins polling `compute_current_lyrics_lines()` on a timer (`v1.2/Files/shazam.py:3060`, `3995`)
7. `periodic_recognition_task()` sleeps `gui.update_interval_ms` (in small chunks, checking `stop_event`) then repeats from step 1

### LED reaction flow

1. `set_status_message()` (called from many points in the recognition cycle) calls `led_controller.set_state(classify_status_state(message))` immediately on the calling thread (`v1.2/Files/shazam.py:3033`)
2. When a new track's accent color is derived (`extract_accent_color()`/`tune_led_color()` during `update_images()`), `led_controller.set_track_color(led_color_hex)` is invoked
3. `LedController._write()` queues/sends `"COLOR r g b"` or `"STATE name"` over serial, deduplicating repeats and buffering commands while the Arduino is mid-reset (`v1.2/Files/led_controller.py:68-119`)
4. The Arduino sketch (`main.cpp`) parses commands in `handleCommand()`, updates `fadeTarget`/`activeState`, and cross-fades the WS2812B strip over `FADE_MS`

**State Management:**
- All "current" application state lives in module-level globals in
  `shazam.py` (config dict, last-known title/artist/album/image path, accent
  color, history list, lyrics state dict, GUI widget/canvas item IDs). There
  is no state container object — functions mutate globals directly via
  `global` declarations.
- Cross-thread state hand-off happens exclusively through the `update_data`
  dict passed into `schedule_gui_update(update_gui, update_data)`; no other
  shared mutable state is written from the background thread except
  filesystem writes (image files, JSON state files) which the GUI thread
  later reads back in.

## Key Abstractions

**Config dict (`config: Dict[str, Any]`):**
- Purpose: single source of truth for all tunables, loaded once at startup
- Examples: `v1.2/Files/config.json`, `load_config()`/`merge_dicts()` in `shazam.py:160-273`
- Pattern: JSON on disk deep-merged over an in-code default dict, so missing keys in a hand-edited `config.json` fall back safely; accessed everywhere as `config['section']['key']`

**Layout info dict (`layout_info: Dict[str, Any]`):**
- Purpose: return value of `update_images()` describing window size, cover-art square geometry, colors, font sizes, and mode flags (fullscreen/cinematic/idle-splash)
- Examples: consumed by `redraw_history_display(layout_info)`, `render_progress_bar()`
- Pattern: ad-hoc dict "DTO" passed between rendering sub-routines instead of a dataclass

**History entry / `song_history_list`:**
- Purpose: in-memory + on-disk record of recently recognized songs with cached cover-art paths
- Examples: `add_to_history()`, `serialize_history_entry()`, `v1.2/Files/history_state.json`
- Pattern: list of dicts capped at `gui.history_max_items_retain`, with a separate `cleanup_old_history_images()` sweep of the `history_images/` directory

**Lyrics state (`lyrics_state: Dict[str, Any]`):**
- Purpose: tracks the currently displayed lyric source (synced LRC vs plain), anchor timestamp for sync, and cached lookups
- Examples: `set_lyrics_state()`, `refine_lyrics_anchor()`, `compute_current_lyrics_lines()`, `v1.2/Files/lyrics_cache.json`
- Pattern: multi-provider fallback chain (lrclib → NetEase) scored by `score_lrclib_candidate()`/`pick_best_scored_candidate()`, with TTL-based JSON cache

**LedController (only class in the codebase):**
- Purpose: encapsulate the one piece of genuinely stateful, connection-oriented I/O (serial port) behind a small public API (`set_track_color`, `set_state`, `close`)
- Examples: `v1.2/Files/led_controller.py`
- Pattern: lazy-connect, command de-duplication, deferred command flush to survive the Arduino's DTR reset-on-connect

## Entry Points

**`v1.2/Files/shazam.py::main()`:**
- Location: `v1.2/Files/shazam.py:4526`
- Triggers: run directly (`python shazam.py`), or via `v1.2/Files/Run.bat` (Windows) / `v1.2/run_macos.sh` (macOS), themselves triggered by `v1.2/Start.bat` or manual shell invocation
- Responsibilities: load config, restore last state, build Tk window, bind events, start `RecognitionThread`, enter `root.mainloop()`

**`v1.2/Files/tests/*` (pytest entry):**
- Location: `v1.2/Files/tests/`, configured by `v1.2/Files/pytest.ini` (`testpaths = tests`)
- Triggers: `pytest` run from `v1.2/Files/`
- Responsibilities: import `shazam` with native-lib modules (`pyaudio`, `screeninfo`, `shazamio`) stubbed out (`tests/test_ui_helpers.py:1-15`), exercise pure helper functions and `LedController` without needing real hardware/network

**Legacy entry points (frozen, not actively developed):**
- `v1.1/Files/SongPi.py` — v1.1 monolith, launched via `v1.1/SongPi.bat`
- `SongPi - Pi version/SongPi.py` — Raspberry Pi–targeted variant (298 lines, no LED/lyrics features)

## Architectural Constraints

- **Threading:** Exactly two long-lived threads: the Tk main thread (GUI +
  event loop) and one daemon `RecognitionThread` running its own `asyncio`
  event loop. The *only* sanctioned cross-thread call is
  `root.after(0, func, *args)` via `schedule_gui_update()`
  (`v1.2/Files/shazam.py:3021`); calling Tk/canvas APIs directly from the
  recognition thread is a bug pattern to avoid. `LedController` additionally
  uses short-lived `threading.Timer` callbacks and its own `threading.Lock`
  for serial writes.
- **Global state:** Nearly all application state is module-level in
  `v1.2/Files/shazam.py` (see "Global State" block starting line 64) — the
  `config` dict, all Tk widget/canvas item IDs, `song_history_list`,
  `lyrics_state`, `lyrics_cache`, accent/LED color, and every animation
  phase/job-id. `led_controller` is also a module-level singleton assigned
  in `main()`.
- **No package/module split:** `shazam.py` is one file; there is no
  `src/` package, no `__init__.py`-based module tree, and no relative
  imports beyond `from led_controller import LedController`. Adding a new
  capability today means adding another top-level function to `shazam.py`
  unless a class boundary is deliberately introduced (as was done for LEDs).
- **Config schema is implicit:** `config.json`'s shape is defined only by
  the default dict inside `load_config()` (`v1.2/Files/shazam.py:170`) and
  by ad-hoc `config['section']['key']` reads throughout the file — there is
  no schema/validation library.

## Anti-Patterns

### Deep dict/global mutation across function boundaries

**What happens:** Dozens of functions declare `global <name>` and mutate
shared dicts/lists in place (`song_history_list`, `lyrics_state`, `config`)
rather than receiving/returning values.
**Why it's wrong:** Makes call order and thread-safety implicit; a function
called from the wrong thread or wrong order can silently corrupt UI state
(e.g., `update_images()` reads `last_track_title` set by `update_gui()` on a
different call stack).
**Do this instead:** New features should thread state through function
parameters/return dicts (as `process_recognition_result()` already does with
its `update_data` return value) rather than adding new globals.

### String-keyed status/state dicts instead of typed values

**What happens:** Status is represented as free-form strings like
`"Ready (Used Cache)"`, `"Error: Cannot open device 3"`, then re-parsed by
`classify_status_state()` (`v1.2/Files/shazam.py:2633`) to derive an LED
state.
**Why it's wrong:** String matching for control flow is fragile — a
copy-edited status message silently changes LED/UI behavior.
**Do this instead:** Use the existing `Literal[...]` typing pattern (already
used elsewhere, e.g. return type hints) or an enum for status categories, and
derive display text from the category rather than the reverse.

## Error Handling

**Strategy:** Defensive, log-and-continue. Nearly every I/O call (audio
device open, network download, file read/write, Tk canvas calls) is wrapped
in `try/except` that logs via `logger.warning`/`logger.exception` and
degrades gracefully (skip this cycle, keep previous image, disable LEDs)
rather than crashing the process.

**Patterns:**
- Network/image download uses bounded retry loops with configurable
  `network.retry_count`/`retry_delay` (`process_recognition_result()`,
  `v1.2/Files/shazam.py:4238-4306`).
- Tk-specific errors (`tk.TclError`) are caught individually around canvas
  operations since the window can be destroyed mid-callback
  (`schedule_gui_update()`, `update_status_display_text()`).
- Hardware I/O (`LedController`) never raises to callers — connection and
  write failures are caught, logged, and the controller silently drops back
  to "unavailable" (`v1.2/Files/led_controller.py:63-86`).
- Top-level guards exist at the thread-runner level
  (`recognition_loop_runner()`) and around the Tk mainloop (`main()`) to log
  unhandled exceptions instead of letting the process die silently.

## Cross-Cutting Concerns

**Logging:** Standard library `logging`, single named logger
`logging.getLogger("SongRecognizer")` shared by `shazam.py` and
`led_controller.py`; format/level configured from `config['logging']`
(`v1.2/Files/shazam.py` `load_config()` defaults, section `logging`).

**Validation:** No schema validation library; `load_config()` deep-merges
user JSON over hardcoded defaults so missing/invalid keys fall back rather
than erroring. Device/audio parameters are validated ad hoc
(`validate_device_channels()`).

**Authentication:** None — Shazam access goes through the unauthenticated
`shazamio` client; lyrics providers (lrclib, NetEase) are public APIs called
with `requests` and no credentials.

---

*Architecture analysis: 2026-09-28*
