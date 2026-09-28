# External Integrations

**Analysis Date:** 2026-09-28

Scope: `v1.2/` (current/active version). All external integrations are keyless public HTTP APIs — there is no authentication provider, no database, and no cloud backend anywhere in this codebase.

## APIs & External Services

**Song Recognition:**
- Shazam — identifies songs from a recorded audio snippet
  - SDK/Client: `shazamio` (`shazamio==0.7.0`, pinned pure-Python build), invoked as `Shazam().recognize(wav_file_path)`
  - Call site: `v1.2/Files/shazam.py:485-499` (`async def recognize_song`)
  - Auth: none (public/unofficial API wrapped by shazamio)
  - Triggered from the main recognition loop: `v1.2/Files/shazam.py:4343` onward (record → recognize → process → schedule update → wait)

**Synced Lyrics (primary):**
- LRCLIB (`https://lrclib.net`) — public lyrics database, returns time-synced LRC lyrics
  - Endpoints used: `GET https://lrclib.net/api/get` (`v1.2/Files/shazam.py:2019`, `lrclib_get`) and `GET https://lrclib.net/api/search` (`v1.2/Files/shazam.py:2034-2044`, `lrclib_search`, with a `q=` free-text fallback if the structured search returns nothing)
  - Client: raw `requests.get` via a shared retry wrapper `_lyrics_http_get` (`v1.2/Files/shazam.py:1990-2007`, one retry on timeout/connection error)
  - Auth: none; sends a custom `User-Agent: SongPi/1.2 (https://github.com/kyol-dony/SongPi)` header (`v1.2/Files/shazam.py:2216`)
  - Candidate ranking: `score_lrclib_candidate` / `pick_best_scored_candidate` (`v1.2/Files/shazam.py:2054-2107`) scores results by title/artist similarity, synced-vs-plain preference, and duration proximity

**Synced Lyrics (fallback):**
- NetEase Cloud Music — unofficial public mirror API, used as a secondary source for timed lyrics when LRCLIB has no match
  - Base URL: configurable via `config.json` → `lyrics.netease_api_base`, defaults to `https://music.xianqiao.wang/neteaseapiv2` (`v1.2/Files/shazam.py:2118`, `v1.2/Files/config.json`)
  - Endpoints: `GET {base}/search` (keyword/track search) then `GET {base}/lyric` (fetch LRC by song id) — `v1.2/Files/shazam.py:2122-2178` (`netease_fallback`)
  - Auth: none
  - Toggle: `config.json` → `lyrics.enable_netease_fallback` (default `true`)
  - Note: relies on a third-party community mirror of NetEase's API rather than an official endpoint — see Dependencies at Risk in `CONCERNS.md`-style analysis

**Cover Art Images:**
- Fetched directly from URLs returned by the Shazam recognition payload (`track_info['images']['coverarthq']` / `['coverart']`), not a separate API
  - Download + retry logic: `v1.2/Files/shazam.py:4230-4270`, streams to a temp file, verifies via `PIL.Image.verify()`, then atomically replaces the display image (`os.replace`)
  - Auth: none

## Data Storage

**Databases:**
- None. No SQL/NoSQL database of any kind is used.

**File Storage:**
- Local filesystem only, all relative to `v1.2/Files/` (script dir) or `v1.2/` (app root):
  - `v1.2/Files/config.json` — runtime configuration (checked into repo as the shipped default; user-editable)
  - `v1.2/Files/image.jpg` / `image_temp.jpg` — current cover art (temp file swapped in atomically)
  - `v1.2/Files/last_state.json` — last successfully identified song, restored on startup
  - `v1.2/Files/history_state.json` — recent song history metadata
  - `v1.2/history_images/` — cached history cover-art thumbnails (disk usage capped/cleaned automatically per README)
  - `v1.2/Files/lyrics_cache.json` — local cache of fetched lyrics (LRCLIB/NetEase results), keyed by title+artist, with TTLs (`config.json` → `lyrics.cache_ttl_hours` / `cache_miss_ttl_hours`)
  - `v1.2/song_history.log` — persistent plain-text log of recognized songs (timestamp, artist, title)

**Caching:**
- In-process + on-disk JSON cache for lyrics lookups (`lyrics_cache.json`, see `cache_lookup`/`cache_store`, `v1.2/Files/shazam.py:1955-1975`), TTL-based (30 days for hits, 1-24h for misses, configurable)
- Local image cache for history thumbnails (no external CDN/cache service)

## Authentication & Identity

**Auth Provider:**
- None. This is a single-user local desktop app with no login, accounts, or session management. All external calls are anonymous/keyless.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Bugsnag/etc.)

**Logs:**
- Python stdlib `logging`, configured via `config.json` → `logging` block (`level`, `format`, `datefmt`; default `INFO`), logger name `"SongRecognizer"` (see `v1.2/Files/led_controller.py:14` and usage throughout `v1.2/Files/shazam.py`)
- Output goes to console/stdout when run interactively (via `Run.bat` / `run_macos.sh`); no centralized log shipping

## CI/CD & Deployment

**Hosting:**
- None — this is a distributed desktop application, not a hosted service. Distribution is via zipped/7z portable builds (`v1.2/SongPi - full Windows.zip`, `SongPi - portable Windows/SongPi - portable Windows.7z`) or running from source.

**CI Pipeline:**
- None detected — no `.github/workflows`, no other CI config found in the repository.

## Environment Configuration

**Required env vars:**
- None. All configuration is via `v1.2/Files/config.json` (not environment variables). No `.env` files are present or referenced.

**Secrets location:**
- Not applicable — no API keys or credentials are used by any integration (Shazam via shazamio, LRCLIB, and the NetEase mirror are all unauthenticated public endpoints).

## Webhooks & Callbacks

**Incoming:**
- None — the app makes only outbound requests; it does not run a server or expose any endpoint.

**Outgoing:**
- None beyond the request/response API calls listed above (no fire-and-forget webhook notifications).

## Hardware Integration (non-network, notable "external" dependency)

**LED Strip Controller (Arduino):**
- USB serial connection (not a network integration, but a physical external device dependency worth flagging for planning purposes)
- Client: `pyserial`, wrapped by `v1.2/Files/led_controller.py` (`LedController` class)
- Protocol: newline-delimited ASCII commands (e.g., `BRIGHTNESS %d`) sent over serial to an Arduino Uno running the FastLED-based sketch in `v1.2/Arduino/SongPiLedStrip/src/main.cpp`
- Config: `config.json` → `led` block (`enabled`, `port`, `baud_rate`, `brightness`, `pixel_count`, `data_pin`, color multipliers, `reset_delay_seconds`)
- Optional/best-effort: disabled by default (`led.enabled: false`); connection failures are caught and logged as warnings, not fatal (`v1.2/Files/led_controller.py:_connect`)

---

*Integration audit: 2026-09-28*
