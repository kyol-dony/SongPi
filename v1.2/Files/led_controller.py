"""Best-effort serial control for SongPi's external LED strip.

The controller owns only the transport and a small line protocol. Lighting
behaviours stay on the microcontroller, so new reactions need no app rewrite.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Optional, Tuple

logger = logging.getLogger("SongRecognizer")
_HEX_COLOR = re.compile(r"^#?([0-9a-fA-F]{6})$")


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
    """Convert a six-digit hex color to an RGB tuple."""
    match = _HEX_COLOR.fullmatch(str(color).strip())
    if not match:
        raise ValueError("color must be a six-digit hex value, e.g. #7c8fff")
    value = match.group(1)
    return tuple(int(value[i:i + 2], 16) for i in range(0, 6, 2))  # type: ignore[return-value]


class LedController:
    """Send newline-delimited lighting commands to an Arduino over USB serial."""
    def __init__(self, settings: Optional[dict[str, Any]] = None) -> None:
        settings = settings or {}
        self.enabled = bool(settings.get("enabled", False))
        self.port = str(settings.get("port", "")).strip()
        self.baud_rate = int(settings.get("baud_rate", 115200))
        self.brightness = max(0, min(255, int(settings.get("brightness", 96))))
        # Opening a USB serial connection resets a stock Uno through DTR. Do
        # not send its first commands until the sketch has reached loop().
        self.reset_delay_seconds = max(0.0, float(settings.get("reset_delay_seconds", 2.0)))
        self._serial: Any = None
        self._lock = threading.Lock()
        self._ready_at = 0.0
        self._pending_commands: list[str] = []
        self._flush_timer: Optional[threading.Timer] = None
        self._last_color: Optional[Tuple[int, int, int]] = None
        self._last_state: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.port)

    def _connect(self) -> bool:
        if not self.is_configured:
            return False
        if self._serial and getattr(self._serial, "is_open", False):
            return True
        try:
            import serial  # Optional until LEDs are enabled.
            self._serial = serial.Serial(self.port, self.baud_rate, timeout=0.2, write_timeout=0.5)
            logger.info("Connected LED controller on %s at %d baud.", self.port, self.baud_rate)
            self._ready_at = time.monotonic() + self.reset_delay_seconds
            self._pending_commands.append("BRIGHTNESS %d" % self.brightness)
            self._schedule_pending_flush()
            return True
        except Exception as error:
            self._serial = None
            logger.warning("LED controller unavailable on %s: %s", self.port, error)
            return False

    def _write(self, command: str) -> bool:
        with self._lock:
            if not self._connect():
                return False
            if time.monotonic() < self._ready_at:
                self._pending_commands.append(command)
                return True
            return self._write_now(command)

    def _write_now(self, command: str) -> bool:
        """Write one command while the caller holds _lock."""
        try:
            self._serial.write((command + "\n").encode("ascii"))
            self._serial.flush()
            return True
        except Exception as error:
            logger.warning("LED command failed; will reconnect later: %s", error)
            self._close_unlocked()
            return False

    def _schedule_pending_flush(self) -> None:
        if self._flush_timer:
            self._flush_timer.cancel()
        self._flush_timer = threading.Timer(self.reset_delay_seconds, self._flush_pending_commands)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush_pending_commands(self) -> None:
        """Deliver commands queued while the Uno was rebooting after port open."""
        with self._lock:
            self._flush_timer = None
            if not self._serial or not getattr(self._serial, "is_open", False):
                return
            wait_seconds = self._ready_at - time.monotonic()
            if wait_seconds > 0:
                self._flush_timer = threading.Timer(wait_seconds, self._flush_pending_commands)
                self._flush_timer.daemon = True
                self._flush_timer.start()
                return
            commands, self._pending_commands = self._pending_commands, []
            for command in commands:
                if not self._write_now(command):
                    break

    def set_track_color(self, color: str) -> bool:
        rgb = hex_to_rgb(color)
        if rgb == self._last_color:
            return True
        if self._write("COLOR %d %d %d" % rgb):
            self._last_color = rgb
            return True
        return False

    def set_state(self, state: str) -> bool:
        """Publish a state extension point; current firmware keeps color solid."""
        normalized = re.sub(r"[^a-z0-9_-]+", "_", state.lower()).strip("_") or "unknown"
        if normalized == self._last_state:
            return True
        if self._write("STATE " + normalized):
            self._last_state = normalized
            return True
        return False

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._flush_timer:
            self._flush_timer.cancel()
        self._flush_timer = None
        self._pending_commands = []
        self._ready_at = 0.0
        # A queued command may have been cached as delivered before the Uno
        # became ready. Clear delivery caches whenever the transport fails or
        # closes so the next redraw/state change reconnects and resends.
        self._last_color = None
        self._last_state = None
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
