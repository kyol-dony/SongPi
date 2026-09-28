# Codebase Concerns

**Analysis Date:** 2026-09-28

## Tech Debt

**Monolithic `shazam.py` (single file owns everything):**
- Issue: The active v1.2 application is a single 4,608-line procedural script that mixes audio capture, network I/O (Shazam/LRCLIB/NetEase), image processing, GUI rendering (Tkinter canvas), animation/tweening, history persistence, lyrics sync, and app lifecycle in one file with no classes and ~100+ top-level functions.
- Files: `v1.2/Files/shazam.py`
- Impact: Any change risks unrelated regressions; hard to unit test most of the logic (GUI, network, and audio are all interleaved with plain functions); onboarding cost is high; `git diff` review is difficult because unrelated concerns live side-by-side.
- Fix approach: Extract cohesive modules — `audio.py` (recording/device selection), `recognition.py` (Shazam calls + retry loop), `lyrics.py` (LRCLIB/NetEase fetch, LRC parsing, sync state), `history.py` (state persistence, cache, cleanup), `ui/` (canvas rendering, animations) — and pass shared state explicitly instead of via module globals.

**Pervasive module-level global state:**
- Issue: ~40 module-level globals (`song_history_list`, `lyrics_state`, `accent_color_hex`, `config`, `led_controller`, all the Tkinter widget/photo-reference IDs, animation phase/job-id trackers, etc.) are mutated via 38 separate `global` statements scattered across the file.
- Files: `v1.2/Files/shazam.py:65-152` (state declarations), throughout (mutation sites)
- Impact: Function behavior depends on hidden shared state, making unit testing and reasoning about control flow difficult; increases risk of stale/inconsistent state after partial failures (e.g., a `PhotoImage` reference cleared in one code path but not another).
- Fix approach: Introduce a small `AppState` / `UiState` dataclass (or a couple of them) passed explicitly to render/update functions instead of relying on `global`.

**Unsynchronized cross-thread mutable state:**
- Issue: The recognition/lyrics/network work runs on a background thread (`recognition_loop_runner` → `periodic_recognition_task`, `v1.2/Files/shazam.py:4461`) which directly mutates shared globals such as `song_history_list` (`add_to_history`, `v1.2/Files/shazam.py:1386-1447`) and `lyrics_state` (`set_lyrics_state`, `v1.2/Files/shazam.py:2280`). The Tkinter main thread reads/renders these same structures (`redraw_history_display`, `v1.2/Files/shazam.py:3567`). There is no `threading.Lock` anywhere in `shazam.py` (only `led_controller.py` uses one).
- Files: `v1.2/Files/shazam.py:1386`, `v1.2/Files/shazam.py:2280`, `v1.2/Files/shazam.py:3567`
- Impact: `schedule_gui_update` (`v1.2/Files/shazam.py:3021`) only marshals *render* calls onto the main thread via `root.after(0, ...)`; the underlying list/dict mutations happen synchronously on the background thread beforehand. A redraw triggered by a timer/resize event while a background mutation is mid-flight (e.g., `song_history_list = song_history_list[:max_mem_items]` reassignment at `v1.2/Files/shazam.py:1419`) can race with iteration in `redraw_history_display`, producing transient `IndexError`/`KeyError` or stale renders. CPython's GIL prevents memory corruption but not logical races.
- Fix approach: Wrap shared-state read/mutate sections in a `threading.Lock`, or better, have the background thread hand off immutable snapshots via a queue that the main thread drains inside `root.after` callbacks.

**Duplicated application logic across three parallel implementations:**
- Issue: The project ships three independently-maintained versions with no shared code: `SongPi - Pi version/SongPi.py` (298 lines), `v1.1/Files/SongPi.py` (1,763 lines), and `v1.2/Files/shazam.py` (4,608 lines). Fixes made in one version (e.g., audio device auto-selection, error handling) are not propagated to the others.
- Files: `SongPi - Pi version/SongPi.py`, `v1.1/Files/SongPi.py`, `v1.2/Files/shazam.py`
- Impact: Bug fixes and feature improvements must be manually re-applied per version, or older versions silently rot; `SongPi - portable Windows/` and `SongPi - Pi version/` ship only as prebuilt archives (`.7z`/`.zip`) with no visible source diff history.
- Fix approach: Consolidate on the v1.2 codebase as the single source of truth, extract genuinely Pi-specific or Windows-portable-specific behavior into config/build variants, and archive or remove the older trees.

**Large binary archives committed to git:**
- Issue: Prebuilt distribution archives are committed directly to the repository, including a 25 MB `.7z` file.
- Files: `SongPi - portable Windows/SongPi - portable Windows.7z` (~25 MB), `SongPi - Pi version/Song Pi - Pi version.zip`, `v1.2/SongPi - full Windows.zip`
- Impact: Bloats clone size and `git` history permanently (removing the file later does not shrink history without a rewrite); binary diffs are meaningless in PRs/code review.
- Fix approach: Move release artifacts to GitHub Releases or a separate distribution channel; keep only source in the repository; use `git filter-repo`/BFG if history size needs to be reclaimed later.

**Oversized functions inside `shazam.py`:**
- Issue: Several functions exceed 300-500 lines and combine multiple responsibilities: `update_images()` (~508 lines, `v1.2/Files/shazam.py:3060-3567`) redraws background, cover art, and all text elements in one pass; `redraw_history_display()` (~361 lines, `v1.2/Files/shazam.py:3567-3927`) handles layout math, image compositing, and canvas item lifecycle together.
- Files: `v1.2/Files/shazam.py:3060`, `v1.2/Files/shazam.py:3567`
- Impact: Hard to test in isolation, hard to reason about partial-failure states (e.g., a `PhotoImage` created but never assigned to a canvas item due to an early return), and any layout tweak risks touching unrelated rendering code.
- Fix approach: Split into layout-calculation (pure, testable) and draw (side-effecting) phases, mirroring the pattern already used for the tested pure helpers in `tests/test_ui_helpers.py`.

**Third-party unofficial API dependency for lyrics fallback:**
- Issue: The NetEase lyrics fallback path calls an unofficial, community-run proxy (`https://music.xianqiao.wang/neteaseapiv2`) rather than an official NetEase or licensed lyrics API.
- Files: `v1.2/Files/config.json:47` (`lyrics.netease_api_base`), `v1.2/Files/shazam.py:2113-2207` (`netease_fallback`)
- Impact: This third-party host is outside the project's control and can disappear, rate-limit, or change response shape without notice, silently degrading the lyrics feature; no fallback/circuit-breaker beyond normal request timeouts is implemented.
- Fix approach: Treat NetEase fallback as best-effort/opt-in (already gated by `lyrics.enable_netease_fallback`), add an explicit failure counter to disable it temporarily after repeated failures, and document the dependency risk for operators.

## Known Bugs

No open, reproducible bug reports were found in-repo (no issue tracker present, `RELEASE_LOG.md` only documents shipped fixes). The following are latent defects observed during code review rather than confirmed field bugs:

**Race in `add_to_history` list pruning vs. concurrent read in `redraw_history_display`:**
- Symptoms: Under rapid successive recognitions, the history panel could momentarily render against a `song_history_list` that has just been reassigned/truncated mid-iteration.
- Files: `v1.2/Files/shazam.py:1417-1420` (mutation), `v1.2/Files/shazam.py:3567` (read)
- Trigger: Two recognition cycles resolving close together while a GUI redraw (e.g., window resize) is also scheduled.
- Workaround: None currently; low probability given the default 5s `update_interval_ms`, but not structurally prevented.

**Bare `except:` swallows all exceptions including `SystemExit`/`KeyboardInterrupt`:**
- Symptoms: A failure in this code path is silently ignored with no log entry, making it invisible in troubleshooting.
- Files: `v1.2/Files/shazam.py:4058`
- Trigger: Whatever exceptional condition occurs inside that block (context: image/canvas cleanup within GUI update code).
- Workaround: None; should be narrowed to a specific exception type (at minimum `except Exception:`) and logged.

## Security Considerations

**Cover-art and lyrics fetched over plain `requests.get` with no TLS pinning/hash verification:**
- Risk: Downloaded cover art and lyrics content come from Shazam-provided CDN URLs and third-party APIs; while URLs are validated to start with `http` (`v1.2/Files/shazam.py:4237`) and images are re-verified via `Image.verify()` before use (`v1.2/Files/shazam.py:4265`), there is no integrity check for lyrics text.
- Files: `v1.2/Files/shazam.py:1991-2012` (`_lyrics_http_get`), `v1.2/Files/shazam.py:4257` (image download)
- Current mitigation: Timeouts, retry limits, image verification via Pillow before promoting the temp file (`os.replace`), and no `verify=False` anywhere (TLS verification is left at `requests` default of `True`).
- Recommendations: None urgent; current mitigations are reasonable for a local desktop app. If the app is ever exposed on a shared/kiosk device, consider sanitizing lyric text before rendering (defense-in-depth) since it is inserted into Tkinter labels, not HTML, so injection risk is minimal.

**No secrets in source, but `config.json` is a plain-text, world-readable settings file:**
- Risk: `v1.2/Files/config.json` and `v1.1/Files/config.json` contain no API keys or credentials (Shazam access is via the unauthenticated `shazamio` library), so there is no credential-leak risk from this file. LED serial port and NetEase base URL are the only "sensitive-ish" values, and both are low risk.
- Files: `v1.2/Files/config.json`, `v1.1/Files/config.json`
- Current mitigation: N/A — no secrets present.
- Recommendations: None required currently; if a future integration needs an API key, keep it out of `config.json` (which several `.py` files read directly and which is not in `.gitignore`) and load it from an environment variable instead.

**Filesystem writes derived from remote/user-influenced strings:**
- Risk: `add_to_history` builds a history image filename from the recognized track title (`v1.2/Files/shazam.py:1394`), which originates from the Shazam API response — an external, only-partially-trusted source.
- Files: `v1.2/Files/shazam.py:1394-1396`
- Current mitigation: The filename is sanitized to alphanumerics/space/underscore only and truncated to 30 characters (`"".join(c for c in track_title if c.isalnum() or c in (' ', '_')).rstrip()[:30]`), which effectively prevents path traversal or shell-special characters.
- Recommendations: None required; sanitization is adequate for this use case.

## Performance Bottlenecks

**Synchronous, blocking audio capture blocks the asyncio recognition loop:**
- Problem: `record_audio()` is a fully synchronous function (blocking `stream.read()` calls in a tight loop) but is awaited from within the async `periodic_recognition_task` without being offloaded to an executor.
- Files: `v1.2/Files/shazam.py:350-481` (`record_audio`), `v1.2/Files/shazam.py:4378` (call site inside the async loop)
- Cause: `record_audio` runs directly on the recognition thread's event loop thread (it's a plain `def`, called directly, not via `loop.run_in_executor`), so for the ~4-6 second recording duration the event loop cannot service other async tasks (e.g., the shutdown-check `asyncio.sleep` polling loop is itself fine, but any future async work added to this loop would stall).
- Improvement path: Not urgent today since the recognition thread has no other concurrent async work, but if additional async tasks are added (e.g., background lyrics prefetch), wrap `record_audio` with `await loop.run_in_executor(None, record_audio, ...)`.

**Full redraw on every recognition cycle and on every resize:**
- Problem: `update_images()` (~508 lines) and `redraw_history_display()` (~361 lines) regenerate blurred backgrounds, halo effects, and re-layout all text/history items from scratch rather than incrementally updating only changed elements.
- Files: `v1.2/Files/shazam.py:3060`, `v1.2/Files/shazam.py:3567`
- Cause: No dirty-checking/memoization beyond a few cached refs (e.g., `ken_burns_last_window_size`); most rendering work re-runs unconditionally.
- Improvement path: Acceptable for the current ~5s update interval and desktop/Pi target, but if `update_interval_ms` is lowered or the app targets lower-powered hardware (Raspberry Pi Zero class), consider caching unchanged image compositing steps (blur, halo) keyed by track identity.

## Fragile Areas

**`shazam.py` as a whole:**
- Files: `v1.2/Files/shazam.py` (all 4,608 lines)
- Why fragile: Single-file, globally-stateful, GUI-and-business-logic-intermixed design (see Tech Debt above) means even small edits (e.g., adjusting layout constants) can have non-obvious effects on unrelated features (lyrics timing, history persistence) that share the same module namespace and `root.after` scheduling queue.
- Safe modification: Prefer additive changes (new config keys with safe defaults via `merge_dicts`, `v1.2/Files/shazam.py:160`) over restructuring existing functions; run the existing pytest suite before and after any change touching `update_images`, `redraw_history_display`, or the lyrics timing functions (`compute_current_lyrics_lines`, `build_synced_lyrics_lines`).
- Test coverage: Only pure/stateless helper functions are tested (see Test Coverage Gaps below); the core recording, recognition, rendering, and persistence logic has zero automated coverage.

**LED controller reconnect/flush timing (`v1.2/Files/led_controller.py`):**
- Files: `v1.2/Files/led_controller.py:50-111`
- Why fragile: Relies on a fixed `reset_delay_seconds` (default 2.0s) to work around the Arduino Uno's DTR-triggered reset on serial connect, queuing commands until a timer fires (`_flush_pending_commands`). If the actual reset time varies (different board, OS, or USB driver), commands sent during the gap are silently queued but the mechanism has no feedback loop to confirm the board is actually ready (no ACK protocol).
- Safe modification: Any change to `_connect`/`_write`/`_schedule_pending_flush` should be tested against real hardware since `tests/test_led_controller.py` only covers `hex_to_rgb` and cache-clearing behavior, not the actual timer/serial flow.
- Test coverage: `v1.2/Files/tests/test_led_controller.py` covers configuration/validation and the `_close_unlocked` cache-reset behavior, but not `_connect`, `_write`, or the reset-delay flush timer (these require a real or mocked `serial.Serial`).

**Lyrics sync anchor drift (`refine_lyrics_anchor`, `compute_current_lyrics_lines`):**
- Files: `v1.2/Files/shazam.py:2317-2344`, `v1.2/Files/shazam.py:2472-2511`
- Why fragile: Lyric timing is estimated from Shazam's reported match offset plus a locally-advanced monotonic clock, with an "anchor smoothing" heuristic (`lyrics.anchor_smoothing_alpha` in config) rather than a real playback-position feed. Any latency variance in recording/recognition (network slowness, retry attempts) directly skews displayed lyric timing with no external correction signal.
- Safe modification: Treat timing constants (`anchor_smoothing_alpha`, `offset_adjust_seconds`) as tunable via config rather than hardcoding; changes to the anchor math should be validated manually against real playback since there's no automated test for synced-lyrics accuracy.
- Test coverage: No tests exist for `parse_synced_lyrics`, `build_synced_lyrics_lines`, `refine_lyrics_anchor`, or `pick_best_lyrics_candidate`.

## Scaling Limits

**Single-track, single-device design:**
- Current capacity: The app is architected for one audio input device and one display window per process (all state is module-level, not per-instance).
- Limit: Cannot run multiple simultaneous recognition sessions (e.g., multi-room display setup) within a single process; would require running multiple OS processes instead.
- Scaling path: Not a near-term concern given the project's scope (single kiosk/display device), but if multi-instance support is ever desired, the global-state refactor mentioned in Tech Debt is a prerequisite.

**Unbounded lyrics cache growth:**
- Current capacity: `lyrics_cache.json` grows by one entry per unique (title, artist) pair recognized, with TTLs (`cache_ttl_hours`, `cache_miss_ttl_hours`) but no evidenced periodic pruning of expired entries beyond lookup-time filtering.
- Files: `v1.2/Files/shazam.py:1937-1981` (`load_lyrics_cache`, `save_lyrics_cache`, `cache_lookup`, `cache_store`)
- Limit: Over long-running deployments (the app is designed to run continuously as a kiosk display), `lyrics_cache.json` can grow indefinitely since expired entries are only skipped on read, not removed on write.
- Scaling path: Add a periodic or startup-time sweep that drops expired cache entries from the in-memory dict before `save_lyrics_cache()` persists it.

## Dependencies at Risk

**`shazamio` pinned to an old version to avoid native-code crashes:**
- Risk: `requirements.txt` pins `shazamio==0.7.0` specifically because newer versions' native `shazamio_core` component segfaults on macOS (documented in `README.md` and `RELEASE_LOG.md`). This blocks picking up any upstream fixes or Shazam API changes in later `shazamio` releases.
- Files: `v1.2/Files/requirements.txt`
- Impact: If Shazam changes its API/protocol in a way that only newer `shazamio` releases handle, recognition could break with no easy upgrade path until the native-crash issue is independently resolved or worked around differently.
- Migration plan: Track upstream `shazamio` issues for the `shazamio_core` segfault; consider vendoring a patched pure-Python recognition path if the pin becomes blocking.

**`numpy==2.1.2` and Python 3.12 hard requirement:**
- Risk: The app requires Python 3.12 specifically because `numpy==2.1.2` (a transitive pin driven by `shazamio==0.7.0`) has prebuilt wheels for 3.12 but not 3.14; `README.md` explicitly warns Python 3.14 will try to compile numpy from source and fail.
- Files: `v1.2/Files/requirements.txt`, `README.md` (macOS setup section)
- Impact: New contributors/users on the latest Python risk a broken setup unless they carefully follow the pinned-version instructions; `.venv313/` present in the repo root suggests this has already caused local environment confusion during development.
- Migration plan: Revisit once `shazamio`/its native dependencies support newer Python and numpy releases; document the constraint prominently (already partially done in README).

**Unofficial NetEase lyrics proxy (see Tech Debt above):**
- Risk: Hard dependency on a third-party, non-contractual API host for lyrics fallback.
- Impact: Silent feature degradation (lyrics fail to load) if the host disappears; already covered above.
- Migration plan: Same as Tech Debt entry — add failure back-off, keep opt-in via config.

## Missing Critical Features

**No automated CI pipeline:**
- Problem: No `.github/workflows/` or other CI configuration was found in the repository; the existing `pytest` suite (`v1.2/Files/tests/`) is not automatically run on push/PR.
- Blocks: Regressions in the tested pure-helper functions (font fitting, color math, LED controller logic) can be merged without detection; there is no automated check that `requirements.txt` installs cleanly on supported platforms.

**No packaging/versioning manifest for the Python app:**
- Problem: There is no `pyproject.toml`/`setup.py` for `v1.2/Files`; the app is distributed as a raw script tree plus batch/shell launchers and prebuilt archives.
- Blocks: No `pip install songpi` style distribution, no dependency lock file (only a loose `requirements.txt` with a few pins), making reproducible installs partially dependent on README instructions being followed exactly.

## Test Coverage Gaps

**Core recognition/audio pipeline is entirely untested:**
- What's not tested: `record_audio`, `recognize_song`, `periodic_recognition_task`, `process_recognition_result`, `recognition_loop_runner` — i.e., the entire audio-capture-to-Shazam-result pipeline.
- Files: `v1.2/Files/shazam.py:350` (`record_audio`), `v1.2/Files/shazam.py:485` (`recognize_song`), `v1.2/Files/shazam.py:4183` (`process_recognition_result`), `v1.2/Files/shazam.py:4342` (`periodic_recognition_task`)
- Risk: Regressions in retry logic, device auto-selection, or result-format handling would only surface at runtime with real hardware/network access.
- Priority: High — this is the app's core value proposition.

**History persistence and cache logic untested:**
- What's not tested: `add_to_history`, `save_history_state`/`load_history_state`, `rebuild_history_state_from_legacy_assets`, `cleanup_old_history_images`, `save_last_state`/`load_last_state`.
- Files: `v1.2/Files/shazam.py:1239-1571`
- Risk: Data loss or corruption of `history_state.json`/`last_state.json` across app restarts would only be caught manually.
- Priority: Medium-High — these functions do disk I/O with several error-handling branches that are easy to break silently.

**Lyrics fetch/scoring/sync logic untested:**
- What's not tested: `lrclib_search`, `score_lrclib_candidate`, `pick_best_lyrics_candidate`, `netease_fallback`, `parse_synced_lyrics`, `parse_lrc_timestamp`, `build_synced_lyrics_lines`, `refine_lyrics_anchor`.
- Files: `v1.2/Files/shazam.py:1811-2472`
- Risk: The LRC parsing and candidate-scoring logic has non-trivial branching (string normalization, similarity scoring, offset tags) that is exactly the kind of logic unit tests are best suited for, yet none exists.
- Priority: Medium — user-visible feature (lyric sync accuracy) with no regression safety net.

**GUI rendering functions untested (acceptable given Tkinter dependency, but layout math could be extracted):**
- What's not tested: `update_images`, `redraw_history_display`, `render_lyrics_labels`, `render_status_pill`, all `tick_*` animation functions.
- Files: `v1.2/Files/shazam.py:3060`, `v1.2/Files/shazam.py:3567`, `v1.2/Files/shazam.py:2516`, `v1.2/Files/shazam.py:2664`
- Risk: Layout/animation regressions (overlapping text, incorrect breakpoint selection) are only caught by manual visual inspection.
- Priority: Low-Medium — `tests/test_ui_helpers.py` already demonstrates the project's pattern of extracting pure layout math (`fit_canvas_title_font`, `detect_layout_breakpoint`, `compute_type_scale`) for testing; more of `update_images`'/`redraw_history_display`'s layout math could be pulled out the same way.

**`v1.1` and `SongPi - Pi version` have zero test coverage:**
- What's not tested: Both older implementations have no `tests/` directory at all.
- Files: `v1.1/Files/SongPi.py`, `SongPi - Pi version/SongPi.py`
- Risk: Low, if these are considered legacy/frozen; high if they are still actively deployed (e.g., Pi version for the Raspberry Pi target implied by the project name).
- Priority: Low if deprecated, Medium if `SongPi - Pi version` is still the recommended path for actual Raspberry Pi hardware (unclear from repo alone whether v1.2 has been validated on a Pi).

---

*Concerns audit: 2026-09-28*
