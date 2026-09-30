# SongPi - Automatic Song Recognition & Visualiser

SongPi is a Python desktop app that listens to the music playing around you, identifies it with Shazam, and turns your screen into a living "now playing" display: full-bleed album art, time-synced lyrics that scroll along with the song, a history of recent tracks, and (optionally) an Arduino LED strip that glows in the colour of the current album.

It runs on Windows, macOS, and Linux (including Raspberry Pi), and is designed to sit fullscreen on a spare monitor, TV, or wall display.

![Fullscreen cinematic layout](readme_images/JVB_fullscreen.png)
![Fullscreen cinematic layout 2](readme_images/divorced-aussie-dad-tunes_fullscreen.png)
![Windowed layout](readme_images/banger_windowed.png)
![Windowed layout 2](readme_images/Oshun-El-eee_windowed.png)

---

## How It Works

1. **Listen.** SongPi records a short clip from your microphone or audio input. If Shazam doesn't find a match, it tries again in the same cycle with a longer recording.
2. **Recognise.** The clip is sent to Shazam (via the [`shazamio`](https://github.com/shazamio/ShazamIO) library), which returns the title, artist, album, cover art, and how far into the song the clip was.
3. **Style.** The cover art is downloaded, and SongPi pulls a dominant accent colour from it. That colour tints the lyrics, progress bar, status pill, halo, and the LED strip.
4. **Fetch lyrics.** Time-synced lyrics are looked up on [LRCLIB](https://lrclib.net), with NetEase as a fallback, and cached on disk.
5. **Display.** The song, lyrics, and history are rendered on a blurred, slowly drifting copy of the album art. The lyric clock is anchored to the moment the audio was captured, so lyrics stay in time with the music.
6. **Repeat.** SongPi keeps listening and updates the display when the song changes.

---

## Features

### Recognition
- **Always-on listening:** SongPi recognises songs continuously and updates the display on its own.
- **Retry with longer capture:** each cycle can record more than once, and retries can use a longer clip, so quiet or late-starting music is still caught.
- **Robust audio handling:** input overflows, closed streams, and empty recordings are handled without crashing.
- **Automatic input selection:** leave `device_index` as `null` and SongPi picks a working input device on its own.

### Time-synced lyrics
- **Multiple sources:** LRCLIB first, using several search strategies and a scoring system to pick the best match. A NetEase lyrics mirror is used as a fallback.
- **Smart matching:** titles and artists are cleaned up before searching. "feat.", "remix", bracketed text, and accents are stripped so more songs find lyrics.
- **Accurate sync:**
  - Playback position is anchored to when the audio was *recorded*, not when Shazam replied.
  - LRC `[offset:]` tags are respected.
  - Repeated recognitions of the same song are smoothed so the lyrics don't jump around.
- **On-disk lyrics cache:** found lyrics are kept for 30 days. Misses are retried after an hour.
- **Fallback:** plain (unsynced) lyrics can be shown if no timed lyrics exist.

### Cinematic display
- **Cinematic layout:** in fullscreen or wide windows, the cover art sits bottom-left, track details sit beside it, lyrics fill the right side, and recent album covers stack above.
- **Responsive layout:** the screen switches between *wide*, *mid*, and *stacked* layouts based on window size and shape. Type sizes scale to match, so it looks right on a 7" Pi screen and a 4K TV alike.
- **Album-driven colour:**
  - Each song's accent colour tints the active lyric line, the progress bar, and a soft halo behind the cover art.
  - A radial vignette keeps text readable on any artwork.
- **Motion and polish:**
  - The blurred backdrop slowly pans and zooms ("Ken Burns" effect) and crossfades when the song changes.
  - The accent colour crossfades between tracks.
  - The active lyric line gently "breathes" with a glow.
  - Lyrics slide and fade as they advance.
- **Status pill:** a rounded indicator with a coloured, pulsing dot shows what SongPi is doing: starting, listening, recognising, ready, no match, or error.
- **Idle splash:** when nothing has been recognised for a while, the display fades to an animated gradient with the SongPi wordmark instead of showing a stale song.
- **Clean typography:**
  - Inter font where available, with fallbacks.
  - Artist names are shown uppercase and letter-spaced.
  - Long titles, albums, and artist names shrink and wrap at word boundaries instead of overlapping or breaking mid-word.
- **Low-power mode:** on Raspberry Pi-class hardware (ARMv7, 4 cores or fewer), heavy animation is turned off automatically. You can also force this with `gui.motion_reduced`.

### History and persistence
- **Recent tracks panel:** recently identified songs are shown with thumbnails. They sit beside the main art in landscape windows, below it in portrait, and stacked above the cover in cinematic mode.
- **Survives restarts:**
  - The history list is saved to `Files/history_state.json`.
  - The last song is saved to `Files/last_state.json`.
  - Both are restored on startup, so the screen never comes up empty.
- **Play log:** every recognised song is appended to `song_history.log` with a timestamp.
- **Tidy disk usage:** cached cover art is cleaned up automatically. `history_max_items_retain` sets how many covers are kept.

### Album-colour LED strip (optional)
- A WS2812B LED strip driven by an Arduino Uno glows in the current album's accent colour.
- It fades smoothly (about 1 second) between colours when the song changes.
- The firmware enforces a hard power cap (400 mA at 5 V) to protect your power supply.
- Saturation and brightness boosts can be tuned for more vivid strips.
- See [LED strip setup](#led-strip-setup-optional) below.

### Controls
- **`Esc`**: switch between fullscreen and windowed mode. Windows can be freely resized.
- **Mouse cursor**: hides automatically after a few seconds of inactivity.

---

## Getting Started

The current version lives in the **`v1.3/`** folder. All commands below are run from there.

> **Python 3.12 is strongly recommended.** SongPi relies on specific versions of `shazamio` (0.7.0) and `numpy` (2.1.2) that are only reliable on 3.12. Newer Python versions can crash or fail to install.

### Windows
1. Install [Python 3.12](https://www.python.org/downloads/release/python-3123/). **Tick "Add python.exe to PATH"** during install.
2. Double-click **`1st time setup.bat`**. It creates a virtual environment in `Files\venv` and installs everything.
3. Double-click **`Start.bat`** to launch SongPi. Use `Start.bat` every time after that.
4. Play some music!

### macOS
1. Install Python 3.12 (from the [python.org installer](https://www.python.org/downloads/) or `brew install python@3.12`).
2. If PyAudio fails to build, run `brew install portaudio` and try again.
3. From the `v1.3` folder, run setup:
   ```bash
   ./setup_macos.sh
   ```
   The script looks for Python 3.12 automatically. To point it at a specific interpreter:
   ```bash
   PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 ./setup_macos.sh
   ```
4. Launch any time with:
   ```bash
   ./run_macos.sh
   ```
5. If the scripts aren't executable, run `chmod +x setup_macos.sh run_macos.sh` once.
6. If you ever get a segfault importing `shazamio_core` or a numpy build error, delete `Files/venv` and re-run `./setup_macos.sh`.

### Linux / Raspberry Pi
1. Install Python 3.12 and PortAudio (e.g. `sudo apt install portaudio19-dev python3-tk`).
2. Create a virtual environment and install dependencies:
   ```bash
   cd v1.3/Files
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Run SongPi:
   ```bash
   python shazam.py
   ```

### Audio input tips
- SongPi needs a working microphone or audio input.
- To identify your computer's *own* audio, set up a loopback device: "Stereo Mix" on Windows, VB-Cable, or BlackHole on macOS.
- Leave `audio.device_index` as `null` to auto-select an input. SongPi logs the available devices at startup if you want to choose a specific one.

---

## Configuration

All settings live in **`v1.3/Files/config.json`**. The defaults work well out of the box; the most useful settings are listed below.

| Section | What it controls | Handy settings |
|---|---|---|
| `audio` | Recording setup | `device_index`, `record_seconds`, `sample_rate` |
| `recognition` | Retry behaviour | `capture_attempts_per_cycle`, `extended_record_seconds`, `retry_delay_ms` |
| `gui` | Look and motion | `blur_strength`, `vignette_intensity`, `accent_halo_intensity`, `ken_burns_enabled`, `motion_reduced`, `idle_splash_enabled`, `idle_splash_after_seconds`, `history_max_items` |
| `lyrics` | Lyrics and cinematic layout | `enabled`, `prefer_synced_lyrics`, `show_plain_lyrics`, `offset_adjust_seconds`, `lines_visible`, `force_cinematic_mode`, `fullscreen_implies_cinematic_mode`, `enable_netease_fallback`, `cache_ttl_hours` |
| `led` | Arduino LED strip | `enabled`, `port`, `brightness`, `saturation_multiplier`, `value_multiplier` |
| `network` | Request timeouts and retries | `timeout`, `retry_count`, `retry_delay` |
| `logging` | Log verbosity and format | `level` |

**Lyrics running early or late?** Adjust `lyrics.offset_adjust_seconds`: positive values shift lyrics later, negative values shift them earlier.

---

## LED Strip Setup (optional)

**You'll need:**
- An Arduino Uno
- A WS2812B strip (30 LEDs by default)
- A 330–470 Ω resistor
- A ~1000 µF capacitor
- A separate 5 V power supply for the strip

1. **Flash the firmware.** Open `v1.3/Arduino/SongPiLedStrip` as a [PlatformIO](https://platformio.org/) project and build/upload the `uno` environment. FastLED is installed automatically.
2. **Wire it up.**
   - Arduino **D6** → strip **DIN**, through the resistor.
   - Arduino **GND** → strip power-supply **GND**. The shared ground is required.
   - Power the strip from the **external 5 V supply**, not the Uno's 5 V pin.
   - Put the capacitor across the strip's supply input.
3. **Enable it in SongPi.** In `Files/config.json`, set `led.enabled` to `true` and `led.port` to your board's serial port: `COM3` on Windows, or `/dev/cu.usbmodem…` on macOS.
4. **Tune it (optional).**
   - `brightness` is 0–255.
   - `saturation_multiplier` makes colours more vivid (`1.0` = unchanged, up to about `1.6`).
   - `value_multiplier` brightens or dims the colour itself.
   - If you change the LED count or data pin, update both the sketch constants and `pixel_count` / `data_pin` in the config.

> ⚠️ The firmware caps power at **400 mA at 5 V** (`MAX_POWER_MILLIAMPS` in `src/main.cpp`). Never raise it above your power supply's continuous current rating.

---

## Troubleshooting

- **No audio devices found / can't open device:** check that your mic is connected and enabled in system settings. Set `audio.device_index` to `null` to auto-select, or pick an index from the device list in the log.
- **Songs aren't being recognised:** make the music louder or move the mic closer, and check your internet connection. Raising `recognition.extended_record_seconds` can help with quiet music.
- **No lyrics for a song:** not every song has synced lyrics on LRCLIB or NetEase. Misses are cached for an hour and then retried. Set `lyrics.show_plain_lyrics` to `true` to show unsynced lyrics when timed ones aren't available.
- **Animations are choppy (e.g. on a Pi):** set `gui.motion_reduced` to `true`.
- **LED strip doesn't light up:**
  - Check `led.port` and that the firmware is flashed.
  - Confirm the shared ground between the Arduino and the strip supply.
  - SongPi waits `led.reset_delay_seconds` (default 2 s) for the Uno to reboot after connecting.
- **Crashes on startup on macOS/Python 3.13+:** use Python 3.12 and rebuild the venv (see macOS setup above).

---

## Running the Tests

SongPi has a pytest suite covering the layout, typography, colour, timing, and LED helper logic.

```bash
cd v1.3/Files
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install pytest
pytest
```

---

## Repository Layout

| Path | What it is |
|---|---|
| `v1.3/` | **Current version**. Use this. |
| `v1.3/Files/shazam.py` | The main app |
| `v1.3/Files/led_controller.py` | Serial link to the Arduino LED strip |
| `v1.3/Files/config.json` | Settings |
| `v1.3/Files/tests/` | pytest suite |
| `v1.3/Arduino/SongPiLedStrip/` | PlatformIO firmware for the LED strip |
| `v1.1/`, `SongPi - Pi version/`, `SongPi - portable Windows/` | Older versions, kept for reference |
| `RELEASE_LOG.md` | Detailed release notes |

---

## What's New

### v1.3 (latest)

**Lyrics and sync overhaul**
- Lyrics now come from multiple sources: LRCLIB with smarter search and match scoring, plus a NetEase fallback.
- Title and artist clean-up means far more songs find lyrics.
- The lyric clock is anchored to when the audio was recorded, respects LRC offset tags, and is smoothed across repeated recognitions. Lyrics stay tightly in sync.
- Lyrics are cached on disk, so songs you've heard before load their lyrics instantly.

**Complete visual redesign**
- Per-song accent colours from the album art, a radial vignette, an accent halo behind the cover, and an accent progress bar.
- A drifting, crossfading "Ken Burns" backdrop, accent crossfades between tracks, a breathing glow on the active lyric, and slide/fade lyric transitions.
- A status pill with a colour-coded, pulsing dot.
- An idle splash screen when nothing is playing.
- A responsive layout system (wide / mid / stacked) with a matching type scale.
- Inter typography, a letter-spaced uppercase artist label, and word-safe text fitting so long names never overlap or break mid-word.
- An automatic low-power profile for Raspberry Pi, plus a manual `motion_reduced` switch.

**Album-colour LED lighting**
- New Arduino/WS2812B firmware and a Python serial controller.
- The strip mirrors the album's accent colour, with smooth 1-second fades and a built-in power cap.

**Quality**
- New pytest suite for the core display and LED logic.
- Updated macOS setup and run scripts.
- `pyserial` added to requirements.

### v1.2
- macOS support with dedicated setup and run scripts.
- Time-synced lyrics from LRCLIB.
- The first cinematic fullscreen layout, with album info and recent covers.
- Multi-attempt recognition with longer retry recordings.
- Song history that persists across restarts, rebuilt from older logs if needed.

### v1.1
- Visual song history panel with adaptive side/below layout and cached artwork.
- The last song is remembered and restored on restart.
- Smarter automatic audio device selection.
- Better font scaling, placeholder art, expanded configuration, logging, and code clean-up.

See [`RELEASE_LOG.md`](RELEASE_LOG.md) for full details.

---

## License

SongPi is released under the [MIT License](LICENSE). See [`NOTICE.md`](NOTICE.md) for authors, third-party licenses, and a disclaimer about the external services, lyrics, and artwork SongPi uses.
