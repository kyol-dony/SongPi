# Notices

SongPi is released under the [MIT License](LICENSE).

## Authors

- **Mildywot**: original SongPi application (2024).
- **Kyle Doney**: v1.2–v1.3 development (2026), including synced lyrics, the cinematic display, and Arduino LED lighting.

## Third-party services

SongPi is an independent, non-commercial project. It is **not affiliated with, endorsed by, or sponsored by** Shazam, Apple Inc., LRCLIB, or NetEase.

- **Song recognition** uses Shazam through the unofficial [`shazamio`](https://github.com/shazamio/ShazamIO) library.
- **Lyrics** come from [LRCLIB](https://lrclib.net). If LRCLIB has none, SongPi tries an unofficial community mirror of NetEase Cloud Music.

Use of these services is subject to their own terms, and they may change or stop working at any time.

## Lyrics, artwork, and song metadata

Song lyrics, album artwork, and track metadata belong to their respective copyright holders.

- SongPi does **not** include or distribute any of this content.
- It is fetched at runtime and shown on the user's own screen for personal use only.
- Local caches (`lyrics_cache.json`, `history_images/`) stay on the user's machine and should not be redistributed.

The MIT License covers SongPi's own source code only. It does not grant any rights to third-party lyrics, artwork, or trademarks.

## Third-party software

SongPi depends on the following open-source packages. They are installed separately and remain under their own licenses.

| Package | License |
|---|---|
| [shazamio](https://github.com/shazamio/ShazamIO) | MIT |
| [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) | MIT |
| [Pillow](https://python-pillow.org/) | MIT-CMU |
| [requests](https://requests.readthedocs.io/) | Apache-2.0 |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [screeninfo](https://github.com/rr-/screeninfo) | MIT |
| [pySerial](https://github.com/pyserial/pyserial) | BSD-3-Clause |
| [audioop-lts](https://github.com/AbstractUmbra/audioop) (Python 3.13+) | PSF-2.0 |
| [FastLED](https://github.com/FastLED/FastLED) (Arduino firmware) | MIT |

## Hardware disclaimer

The optional LED strip setup involves external power supplies and wiring. Follow the safety notes in the README, and do not exceed your power supply's rated current. As stated in the MIT License, the software is provided "as is", without warranty of any kind. The authors are not liable for damage to hardware or property.
