# Release Log

## April 9, 2026

This release rolls the `v1.1` functionality into `SongPi_full_Windows` and expands the app into a more complete cross-platform display client with synced lyrics, persistent history, and a cinematic fullscreen layout.

### macOS support

- Added `SongPi_full_Windows/setup_macos.sh` and `SongPi_full_Windows/run_macos.sh` so the project can be set up and launched on macOS without using the Windows batch files.
- The macOS setup flow now prefers Python `3.12` automatically, rejects unsupported interpreter versions early, and uses the venv interpreter directly for dependency installation.
- The setup script installs the `numpy` wheel explicitly before the rest of the requirements so pip does not fall back to an unstable source build on macOS.
- The runtime avoids Linux-only audio environment changes on macOS and Windows by only applying the ALSA hint when running on Linux.

### Recognition and audio capture

- Recognition is no longer a single short capture attempt. Each cycle can record more than once before giving up.
- Retry captures can use a longer sample length than the first attempt. This makes recognition more tolerant of low-volume or late-starting music.
- Audio recording now handles input overflows more safely and avoids crashing when a stream closes unexpectedly or produces no usable frames.
- The recognition controls are exposed through config:
  `recognition.capture_attempts_per_cycle`
  `recognition.retry_delay_ms`
  `recognition.extended_record_seconds`
  `recognition.use_extended_recording_on_retry`

### LRCLIB synced lyrics

- Added LRCLIB integration for lyric lookup after a song is recognized.
- The client scores LRCLIB results by title and artist similarity and prefers candidates that contain `syncedLyrics`.
- If synced lyrics are available, the app parses the LRC timestamps and builds the visible lyric window from the current playback time.
- The lyric clock is estimated from Shazam’s reported match offset and then advanced locally with a monotonic timer.
- Plain unsynced lyrics remain available as a fallback path, but synced lyrics are preferred by default.
- The main lyric timing controls are:
  `lyrics.offset_adjust_seconds`
  `lyrics.refresh_interval_ms`
  `lyrics.prefer_synced_lyrics`
  `lyrics.show_plain_lyrics`

### Cinematic display mode

- Added a cinematic wide-screen layout intended for fullscreen display boards.
- In cinematic mode, the current cover art sits in the lower-left corner, track metadata sits immediately to its right, and the lyric panel occupies the right side of the screen.
- Cinematic mode can be entered automatically from fullscreen or wide-window geometry, and can also be forced through config.
- The layout is controlled by:
  `lyrics.force_cinematic_mode`
  `lyrics.fullscreen_implies_cinematic_mode`
  `lyrics.panel_gap_ratio`
  `lyrics.panel_margin_ratio`

### Current track metadata block

- Added album extraction and display between the song title and artist line.
- Added inline metadata icons for the current song block so the symbols move with the text instead of drifting independently when the title wraps.
- The current-song title now scales down dynamically until its wrapped height fits the allocated metadata region.
- Album, artist, and status lines are positioned from the title’s actual rendered height instead of from an assumed single-line title. This prevents overlap on long track names.

### Lyrics rendering improvements

- Synced lyric rows can now wrap onto multiple visual lines without colliding with the next timed lyric row.
- The lyric renderer measures each displayed lyric block and positions the next block from the previous block’s real bottom edge.
- Each lyric row can shrink independently to stay within its allotted height while still preserving the correct synced line order.

### History panel and persistence

- Song history is no longer session-only. The visible history stack is now persisted to `SongPi_full_Windows/Files/history_state.json`.
- On startup, the app restores recent history from the saved JSON state.
- If no JSON history exists yet, the app can rebuild a usable history list from legacy `history_images/` files and `song_history.log`.
- Cinematic mode now shows recent album covers above the current cover, with smaller title and artist text beside each thumbnail.
- History titles also scale down dynamically so long titles do not overlap their artist lines.
- Relevant files:
  `SongPi_full_Windows/Files/history_state.json`
  `SongPi_full_Windows/history_images/`
  `SongPi_full_Windows/song_history.log`

### State restoration

- The app continues to save and restore the last recognized song so the display does not come up empty after a restart.
- Last known track title, artist, album, and cover art are stored in `SongPi_full_Windows/Files/last_state.json`.

### Dependency and runtime stability

- The project pins `shazamio==0.7.0` to avoid the crashing native `shazamio_core` path seen on newer Python builds.
- `audioop-lts` is used on Python `3.13+` to replace the removed stdlib `audioop` module when needed.
- Shared dependencies are consolidated in `SongPi_full_Windows/Files/requirements.txt` so Windows and macOS installations stay aligned.

### Practical result

- The app can now run on Windows and macOS.
- Recognition is more tolerant of missed matches.
- Lyrics can display in a timed, visually structured way.
- Fullscreen mode behaves more like a dedicated music display board.
- History, artwork, and last-song state survive restarts instead of resetting every session.
