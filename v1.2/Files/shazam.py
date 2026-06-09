# --- START OF FILE shazam.py ---

import pyaudio
import wave
import asyncio
import tkinter as tk
from tkinter import font as tkFont
from shazamio import Shazam
import requests
from PIL import Image, ImageTk, ImageFilter, ImageStat, ImageDraw, ImageFont
import io
import os
import json
import math
import re
import unicodedata
from screeninfo import get_monitors
import threading
import logging
import tempfile
from datetime import datetime
import shutil
import sys
import time
from typing import Optional, Dict, Any, Tuple, List, Literal, Union
from pathlib import Path

# Only set ALSA hint on Linux (avoids breaking macOS/Windows)
if sys.platform.startswith("linux"):
    os.environ.setdefault('PA_ALSA_PLUGHW', '1')

# --- Constants ---
# Get the directory containing this script (shazam.py) -> Files/
SCRIPT_DIR = Path(__file__).parent.resolve()
# Get the parent directory of the script's directory -> SongPi_Root_Folder/
APP_ROOT_DIR = SCRIPT_DIR.parent

CONFIG_FILENAME = 'config.json'
IMAGE_FILENAME = 'image.jpg'
TEMP_IMAGE_FILENAME = 'image_temp.jpg'
HISTORY_IMAGE_DIR = 'history_images'      # Relative name, base is APP_ROOT_DIR
LAST_STATE_FILENAME = 'last_state.json'
HISTORY_STATE_FILENAME = 'history_state.json'
LYRICS_CACHE_FILENAME = 'lyrics_cache.json'
SONG_HISTORY_FILENAME = 'song_history.log' # Relative name, base is APP_ROOT_DIR

# Paths relative to the script's location (inside Files/)
CONFIG_PATH = SCRIPT_DIR / CONFIG_FILENAME
IMAGE_PATH = SCRIPT_DIR / IMAGE_FILENAME
TEMP_IMAGE_PATH = SCRIPT_DIR / TEMP_IMAGE_FILENAME # Keep temp file relative to script
LAST_STATE_FILE_PATH = SCRIPT_DIR / LAST_STATE_FILENAME
HISTORY_STATE_FILE_PATH = SCRIPT_DIR / HISTORY_STATE_FILENAME
LYRICS_CACHE_FILE_PATH = SCRIPT_DIR / LYRICS_CACHE_FILENAME

# Paths relative to the application root (one level up from script)
HISTORY_IMAGE_DIR_PATH = APP_ROOT_DIR / HISTORY_IMAGE_DIR
SONG_HISTORY_FILE_PATH = APP_ROOT_DIR / SONG_HISTORY_FILENAME

MIN_WINDOW_WIDTH = 250
MIN_WINDOW_HEIGHT = 200

# --- Global State ---
config: Dict[str, Any] = {}
root: Optional[tk.Tk] = None
canvas: Optional[tk.Canvas] = None
title_label_id: Optional[int] = None
album_label_id: Optional[int] = None
artist_label_id: Optional[int] = None
status_label_id: Optional[int] = None
status_pill_bg_id: Optional[int] = None
status_pill_dot_id: Optional[int] = None
progress_bar_track_id: Optional[int] = None
progress_bar_fill_id: Optional[int] = None
lyrics_primary_label_id: Optional[int] = None
lyrics_secondary_label_id: Optional[int] = None
lyrics_tertiary_label_id: Optional[int] = None
coverart_item_id: Optional[int] = None
cover_halo_photo_ref: Optional["ImageTk.PhotoImage"] = None
cover_halo_item_id: Optional[int] = None

accent_color_hex: str = "#7c8fff"   # Cover-art derived accent; updated per track.
ui_font_family_cache: Optional[str] = None
status_pulse_phase: float = 0.0
status_pulse_job_id: Optional[str] = None
status_pill_layout: Dict[str, Any] = {}   # Cached args for re-rendering on text change

lyric_glow_phase: float = 0.0
lyric_glow_job_id: Optional[str] = None

lyric_transition_state: Dict[str, Any] = {
    "active": False,
    "start_monotonic": 0.0,
    "duration": 0.32,
    "last_index": -1,
}

last_recognition_monotonic: float = 0.0   # Updated when a match resolves.

track_change_state: Dict[str, Any] = {
    "active": False,
    "start_monotonic": 0.0,
    "duration": 0.3,
    "previous_accent": "#7c8fff",
}
track_change_job_id: Optional[str] = None

ken_burns_frame_a_ref: Optional["ImageTk.PhotoImage"] = None
ken_burns_frame_b_ref: Optional["ImageTk.PhotoImage"] = None
ken_burns_item_a: Optional[int] = None
ken_burns_item_b: Optional[int] = None
ken_burns_phase: float = 0.0
ken_burns_direction: int = 1
ken_burns_job_id: Optional[str] = None
ken_burns_last_window_size: Tuple[int, int] = (0, 0)

idle_splash_active: bool = False
idle_splash_bg_id: Optional[int] = None
idle_splash_bg_photo_ref: Optional["ImageTk.PhotoImage"] = None
idle_splash_wordmark_id: Optional[int] = None

bg_photo_ref: Optional[ImageTk.PhotoImage] = None
square_photo_ref: Optional[ImageTk.PhotoImage] = None
history_photo_refs: List[Dict[str, Any]] = []
lyrics_layout_cache: Dict[str, Any] = {}

last_track_title: str = ""
last_album_name: str = ""
last_artist_name: str = ""
last_persistent_image_path: Optional[str] = None
current_status_message: str = "Initialising..."
song_history_list: List[Dict[str, Any]] = [] # In-memory list of recent songs

resize_job_id: Optional[str] = None
cursor_hide_timer_id: Optional[str] = None
lyrics_update_job_id: Optional[str] = None
recognition_thread: Optional[threading.Thread] = None
recognition_thread_stop_event = threading.Event()

logger = logging.getLogger("SongRecognizer")

lyrics_cache: Dict[str, Any] = {}

lyrics_state: Dict[str, Any] = {
    "track_key": None,
    "source": None,
    "synced_lines": [],
    "plain_lyrics": "",
    "display_lines": [],
    "anchor_monotonic": None,
    "anchor_song_seconds": 0.0,
    "lrc_offset_seconds": 0.0,
}


# --- Configuration Loading ---
def merge_dicts(source: Dict, destination: Dict) -> Dict:
    """Recursively merge source dict into destination dict."""
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            merge_dicts(value, node)
        else:
            destination[key] = value
    return destination

def load_config() -> Dict[str, Any]:
    """Loads configuration from JSON file, providing defaults."""
    defaults = {
        "audio": {
            "format": "paInt16", "channels": 1, "sample_rate": 48000,
            "chunk_size": 8192, "record_seconds": 4, "device_index": None
        },
        "recognition": {
            "capture_attempts_per_cycle": 2,
            "retry_delay_ms": 750,
            "extended_record_seconds": 6,
            "use_extended_recording_on_retry": True
        },
        "gui": {
            "update_interval_ms": 5000, "blur_strength": 15, "border_size_ratio": 0.15,
            "base_font_size": 12, "history_max_items": 5, # Max items displayed
            "history_art_size": 60, "history_item_padding": 10,
            "history_x_offset": 20, "history_y_offset": 20,
            "history_font_size_ratio": 0.7, "history_min_side_width": 300,
            "layout_side_min_buffer": 50, "layout_below_min_buffer": 50,
            "status_font_size_ratio": 0.8, # Base ratio before halving
            "history_max_items_retain": 20, # Max items to keep images for on disk
            "vignette_intensity": 0.55,
            "ken_burns_enabled": True,
            "motion_reduced": False,
            "idle_splash_enabled": True,
            "idle_splash_after_seconds": 10,
            "accent_halo_intensity": 0.35,
        },
        "network": {"timeout": 7, "retry_count": 3, "retry_delay": 2},
        "lyrics": {
            "enabled": True,
            "show_plain_lyrics": False,
            "prefer_synced_lyrics": True,
            "lines_visible": 3,
            "force_cinematic_mode": True,
            "fullscreen_implies_cinematic_mode": True,
            "refresh_interval_ms": 250,
            "max_visible_lines": 3,
            "font_scale": 0.75,
            "width_ratio": 0.8,
            "offset_adjust_seconds": 0.0,
            "anchor_smoothing_alpha": 0.35,
            "enable_netease_fallback": True,
            "netease_api_base": "https://music.xianqiao.wang/neteaseapiv2",
            "cache_ttl_hours": 720,
            "cache_miss_ttl_hours": 1,
            "fetch_timeout_seconds": 15,
            "panel_gap_ratio": 0.04,
            "panel_margin_ratio": 0.05,
            "cinematic_history_max_items": 4,
            "cinematic_history_scale": 0.44,
            "cinematic_history_gap": 12,
            "cinematic_history_title_scale": 0.15,
            "cinematic_history_artist_scale": 0.12
        },
        "logging": {
             "level": "INFO",
             "format": "%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s",
             "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    }
    loaded_config = {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            loaded_config = json.load(f)
        logger.debug(f"Configuration loaded from {CONFIG_PATH}")
    except FileNotFoundError:
        logger.warning(f"Configuration file not found at {CONFIG_PATH}. Using default settings.")
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding configuration file {CONFIG_PATH}: {e}. Using default settings.")

    final_config = defaults.copy()
    merge_dicts(loaded_config, final_config)

    log_cfg = final_config.get("logging", defaults["logging"])
    log_level_str = log_cfg.get("level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    if not logging.getLogger().hasHandlers():
         logging.basicConfig(level=log_level,
                            format=log_cfg.get("format"),
                            datefmt=log_cfg.get("datefmt"),
                            stream=sys.stdout)
         logger.info(f"Logging configured at level {log_level_str}.")
    else:
         logging.getLogger().setLevel(log_level)
         logger.info(f"Logging level possibly updated to {log_level_str}.")

    try:
        HISTORY_IMAGE_DIR_PATH.mkdir(parents=True, exist_ok=True)
        logger.info(f"History image directory checked/created: {HISTORY_IMAGE_DIR_PATH}")
    except OSError as e:
        logger.error(f"Could not create history image directory {HISTORY_IMAGE_DIR_PATH}: {e}")

    return final_config


# --- Audio Handling ---
def list_audio_devices() -> List[Tuple[int, str, int]]:
    """Lists available input audio devices."""
    audio = None
    devices = []
    try:
        logger.debug("Initializing PyAudio to list devices...")
        audio = pyaudio.PyAudio()
        host_api_info = audio.get_host_api_info_by_index(0)
        num_devices = host_api_info.get('deviceCount', 0)
        logger.debug(f"Host API reports {num_devices} devices.")
        for i in range(num_devices):
            try:
                device_info = audio.get_device_info_by_host_api_device_index(0, i)
                if device_info.get('maxInputChannels', 0) > 0:
                     logger.debug(f"  Device {i}: {device_info['name']} (In:{device_info['maxInputChannels']}, Out:{device_info['maxOutputChannels']})")
                     devices.append((i, device_info['name'], device_info['maxInputChannels']))
            except Exception as e:
                logger.warning(f"Could not query device index {i}: {e}")
        logger.info(f"Found {len(devices)} input devices.")
    except Exception as e:
         logger.error(f"Error listing audio devices: {e}", exc_info=True)
    finally:
        if audio:
            audio.terminate()
            logger.debug("PyAudio terminated after listing devices.")
    return devices

def validate_device_channels(device_index: int, required_channels: int) -> bool:
    """Checks if a device index is valid and has enough input channels."""
    audio = None
    is_valid = False
    try:
        logger.debug(f"Validating device index {device_index} for {required_channels} channels...")
        audio = pyaudio.PyAudio()
        device_info = audio.get_device_info_by_index(device_index)
        actual_channels = device_info.get('maxInputChannels', 0)
        is_valid = actual_channels >= required_channels
        logger.debug(f"Device {device_index} ('{device_info.get('name', 'N/A')}') has {actual_channels} channels. Valid: {is_valid}")
    except OSError as e:
        logger.warning(f"Device index {device_index} seems invalid or inaccessible: {e}")
    except Exception as e:
        logger.error(f"Error validating device {device_index}: {e}")
    finally:
        if audio:
            audio.terminate()
            logger.debug(f"PyAudio terminated after validating device {device_index}.")
    return is_valid

def select_input_device(required_channels: int) -> Optional[int]:
    """Automatically selects the first suitable input device."""
    logger.info("Attempting to auto-select an input device...")
    devices = list_audio_devices()
    if not devices:
        logger.error("No input audio devices found during auto-selection.")
        return None
    preferred_keywords = ["pulse", "default", "sampler", "loopback", "monitor", "what u hear", "stereo mix"]
    suitable_devices = []
    other_suitable_devices = []
    for i, name, channels in devices:
        if channels >= required_channels:
            if any(keyword in name.lower() for keyword in preferred_keywords):
                suitable_devices.append((i, name))
            else:
                other_suitable_devices.append((i, name))
    if suitable_devices:
        selected_index, device_name = suitable_devices[0]
        logger.info(f"Auto-selected preferred input device: Index {selected_index} ('{device_name}')")
        return selected_index
    elif other_suitable_devices:
         selected_index, device_name = other_suitable_devices[0]
         logger.info(f"Auto-selected input device: Index {selected_index} ('{device_name}')")
         return selected_index
    else:
        logger.error(f"No input device found with required channels ({required_channels}). Available devices logged previously.")
        return None

def record_audio(record_seconds_override: Optional[float] = None) -> Tuple[Optional[str], Optional[float]]:
    """Records audio for a configured duration to a temporary WAV file.

    Returns (wav_path, record_start_monotonic). record_start_monotonic is the
    time.monotonic() value taken immediately before the first audio frame was
    captured — used downstream to subtract recording + recognition latency from
    the lyrics sync anchor.
    """
    global current_status_message
    schedule_gui_update(set_status_message, "Listening...")
    audio_cfg = config['audio']
    dev_index = audio_cfg.get('device_index')
    chans = audio_cfg['channels']
    samp_rate = audio_cfg['sample_rate']
    record_secs = record_seconds_override if record_seconds_override is not None else audio_cfg['record_seconds']
    chunk = audio_cfg['chunk_size']
    audio = None
    try:
        py_audio_format = getattr(pyaudio, audio_cfg['format'])
    except AttributeError:
        logger.error(f"Invalid PyAudio format: {audio_cfg['format']}")
        schedule_gui_update(set_status_message, "Error: Invalid audio format")
        return None, None

    selected_device_index = dev_index
    if selected_device_index is None or not validate_device_channels(selected_device_index, chans):
        if selected_device_index is not None:
            logger.warning(f"Configured device index {selected_device_index} invalid/insufficient. Auto-selecting.")
        else:
            logger.info("No device index configured. Auto-selecting.")
        selected_device_index = select_input_device(chans)
        if selected_device_index is None:
            schedule_gui_update(set_status_message, "Error: No suitable audio device")
            return None, None
        else:
            config['audio']['device_index'] = selected_device_index

    stream = None
    temp_wav_path: Optional[str] = None
    record_start_monotonic: Optional[float] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_f:
            temp_wav_path = temp_f.name
        logger.debug(f"Created temporary WAV file: {temp_wav_path}")
        logger.debug("Initializing PyAudio for recording...")
        audio = pyaudio.PyAudio()
        logger.debug(f"Opening audio stream on device {selected_device_index}...")
        stream = audio.open(format=py_audio_format, rate=samp_rate, channels=chans,
                            input_device_index=selected_device_index, input=True, frames_per_buffer=chunk)
        logger.info(f"Recording started on device {selected_device_index}...")
        frames = []
        num_chunks_to_record = int((samp_rate / chunk) * record_secs)
        record_start_monotonic = time.monotonic()
        for i in range(num_chunks_to_record):
            if recognition_thread_stop_event.is_set():
                logger.info("Recording stopped early by shutdown signal.")
                schedule_gui_update(set_status_message, "Shutting down...")
                safe_remove(temp_wav_path, "temp WAV on cancelled recording")
                return None, None
            try:
                data = stream.read(chunk, exception_on_overflow=False)
                frames.append(data)
            except IOError as e:
                if e.errno == pyaudio.paInputOverflowed:
                    logger.warning("Input overflowed during recording.")
                else:
                    logger.error(f"IOError during stream read: {e}")
                    schedule_gui_update(set_status_message, "Error: Audio input failed")
                    safe_remove(temp_wav_path, "temp WAV on IO read error")
                    return None, None
            except Exception as e:
                logger.exception(f"Unexpected error reading audio stream: {e}")
                schedule_gui_update(set_status_message, "Error: Audio read failed")
                safe_remove(temp_wav_path, "temp WAV on unexpected read error")
                return None, None
        logger.info(f"Recording finished ({len(frames)} chunks captured).")
    except OSError as e:
        logger.error(f"OSError opening stream on device {selected_device_index}: {e}")
        schedule_gui_update(set_status_message, f"Error: Cannot open device {selected_device_index}")
        safe_remove(temp_wav_path, "temp WAV on stream open error")
        return None, None
    except Exception as e:
        logger.exception(f"Unexpected error during recording: {e}")
        schedule_gui_update(set_status_message, "Error: Recording failed")
        safe_remove(temp_wav_path, "temp WAV on unexpected setup error")
        return None, None
    finally:
        if stream:
            try:
                if stream.is_active(): stream.stop_stream()
                stream.close()
                logger.debug("Audio stream stopped/closed.")
            except Exception as e:
                logger.warning(f"Error closing audio stream: {e}")
        if audio:
            audio.terminate()
            logger.debug("PyAudio terminated after recording.")

    if temp_wav_path and frames:
        logger.debug(f"Writing {len(frames)} frames to {temp_wav_path}")
        audio_instance_for_size = None
        try:
            audio_instance_for_size = pyaudio.PyAudio()
            sample_width = audio_instance_for_size.get_sample_size(py_audio_format)

            with wave.open(temp_wav_path, 'wb') as wave_file_obj:
                 wave_file_obj.setnchannels(chans)
                 wave_file_obj.setsampwidth(sample_width)
                 wave_file_obj.setframerate(samp_rate)
                 wave_file_obj.writeframes(b''.join(frames))
            logger.info(f"Audio saved successfully to: {temp_wav_path}")
            return temp_wav_path, record_start_monotonic
        except wave.Error as e:
            logger.error(f"Wave library error writing WAV file {temp_wav_path}: {e}")
            schedule_gui_update(set_status_message, "Error: Could not save audio")
            safe_remove(temp_wav_path, "temp WAV on wave write error")
            return None, None
        except Exception as e:
             logger.exception(f"Unexpected error writing WAV file: {e}")
             schedule_gui_update(set_status_message, "Error: Saving audio failed")
             safe_remove(temp_wav_path, "temp WAV on unexpected write error")
             return None, None
        finally:
            if audio_instance_for_size:
                audio_instance_for_size.terminate()

    else:
        if not frames:
            logger.warning("No audio frames captured.")
            schedule_gui_update(set_status_message, "Error: No audio captured")
        safe_remove(temp_wav_path, "temp WAV when no frames recorded")
        return None, None


# --- Song Recognition ---
async def recognize_song(wav_file_path: str) -> Optional[Dict[str, Any]]:
    """Recognizes the song from a WAV file using Shazamio."""
    schedule_gui_update(set_status_message, "Recognizing...")
    shazam = Shazam()
    max_retries = config['network']['retry_count']
    retry_delay = config['network']['retry_delay']
    result = None
    for attempt in range(max_retries):
        if recognition_thread_stop_event.is_set():
            logger.info("Recognition cancelled by shutdown.")
            schedule_gui_update(set_status_message, "Shutting down...")
            return None
        try:
            logger.info(f"Attempting recognition (Attempt {attempt + 1}/{max_retries})...")
            new_result = await shazam.recognize(wav_file_path)
            logger.debug(f"Raw result (Attempt {attempt+1}): {new_result}")
            if isinstance(new_result, dict):
                 if 'track' in new_result and new_result['track']:
                     logger.info("Recognition successful.")
                     result = new_result
                     break
                 elif 'matches' in new_result and not new_result.get('matches'):
                     logger.info("Recognition: No match.")
                     result = new_result
                     break
                 else:
                     if 'track' in new_result and not new_result['track']:
                         logger.info("Recognition: Got result structure but no track info (effectively no match).")
                         result = {'matches': []}
                         break
                     else:
                         logger.warning(f"Recognition attempt {attempt + 1} unexpected format/content: {new_result}")

            else:
                 logger.warning(f"Recognition attempt {attempt + 1} returned non-dict type: {type(new_result)}")
        except Exception as e:
            logger.error(f"Recognition attempt {attempt + 1} failed: {e}", exc_info=False)
            if attempt < max_retries - 1:
                 schedule_gui_update(set_status_message, f"Retrying ({attempt+2})...")
                 try:
                     await asyncio.sleep(retry_delay)
                 except asyncio.CancelledError:
                     logger.info("Asyncio sleep cancelled during retry.")
                     return None
            else:
                logger.error("Max retry attempts reached for recognition.")
                schedule_gui_update(set_status_message, "Error: Recognition failed")
                result = None
                break
    return result


# --- Image Processing ---
def create_blurred_background(source_image_path: Path, target_width: int, target_height: int, blur_strength: int) -> Optional[Image.Image]:
    """Creates a blurred, cropped, and resized background image."""
    if not source_image_path.is_file():
        logger.warning(f"Source for blur does not exist: {source_image_path}")
        return None
    try:
        logger.debug(f"Creating blurred background from: {source_image_path}")
        with Image.open(source_image_path) as original_image:
            original_image = original_image.convert('RGB')
            blurred_image = original_image.filter(ImageFilter.GaussianBlur(blur_strength))
            source_aspect = original_image.width / original_image.height
            target_aspect = target_width / target_height

            if target_aspect > source_aspect:
                new_width = target_width
                new_height = int(new_width / source_aspect)
            else:
                new_height = target_height
                new_width = int(new_height * source_aspect)

            blurred_image = blurred_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
            right = left + target_width
            bottom = top + target_height

            blurred_image = blurred_image.crop((left, top, right, bottom))
            logger.debug("Blurred background created.")
            return blurred_image
    except FileNotFoundError:
        logger.error(f"FileNotFound during blur (should be caught earlier): {source_image_path}")
        return None
    except Exception as e:
        logger.exception(f"Error creating blurred background from {source_image_path}: {e}")
        return None

def calculate_brightness(image: Image.Image) -> float:
    """Calculates the perceived brightness of an image (0.0 to 1.0)."""
    try:
        grayscale_image = image.convert('L')
        stat = ImageStat.Stat(grayscale_image)
        brightness = stat.mean[0] / 255.0
        logger.debug(f"Calculated brightness: {brightness:.2f}")
        return brightness
    except Exception as e:
        logger.warning(f"Could not calculate brightness: {e}")
        return 0.5


# --- Visual polish helpers (typography, accent color, vignette) ---

UI_FONT_PREFERENCE = [
    "Inter",
    "SF Pro Text",
    "Segoe UI Variable",
    "Segoe UI",
    "Roboto",
    "Noto Sans",
    "Helvetica Neue",
    "Helvetica",
    "Arial",
]


def get_ui_font_family() -> str:
    """Returns the best-available UI font from a curated fallback chain.

    Resolved once per process; falls back to Tk's default if nothing matches."""
    global ui_font_family_cache
    if ui_font_family_cache is not None:
        return ui_font_family_cache
    chosen = "Arial"
    try:
        available = {name.lower() for name in tkFont.families()}
        for candidate in UI_FONT_PREFERENCE:
            if candidate.lower() in available:
                chosen = candidate
                break
    except tk.TclError:
        pass
    ui_font_family_cache = chosen
    logger.info(f"UI font family: {chosen}")
    return chosen


def mix_rgb(rgb_a: Tuple[int, int, int], rgb_b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Linear interpolate two RGB tuples. t=0 → a, t=1 → b."""
    t = max(0.0, min(1.0, t))
    return (
        int(rgb_a[0] + (rgb_b[0] - rgb_a[0]) * t),
        int(rgb_a[1] + (rgb_b[1] - rgb_a[1]) * t),
        int(rgb_a[2] + (rgb_b[2] - rgb_a[2]) * t),
    )


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(rgb[0]))),
        max(0, min(255, int(rgb[1]))),
        max(0, min(255, int(rgb[2]))),
    )


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (124, 143, 255)


SCRIM_RGB: Tuple[int, int, int] = (10, 10, 12)  # #0a0a0c — same as canvas bg fallback.


def dim_hex(value: str, amount: float) -> str:
    """Blends a hex color toward black by `amount` (0..1). amount=1 → black."""
    rgb = hex_to_rgb(value)
    return rgb_to_hex(mix_rgb(rgb, (0, 0, 0), amount))


def simulate_alpha_on_dark(value: str, alpha: float) -> str:
    """Tk text has no alpha — simulate by blending the color toward the dark scrim.
    alpha=1.0 returns the color unchanged; alpha=0.0 returns the scrim color."""
    alpha = max(0.0, min(1.0, alpha))
    return rgb_to_hex(mix_rgb(SCRIM_RGB, hex_to_rgb(value), alpha))


def extract_accent_color(image: Image.Image) -> str:
    """Picks a vibrant accent color from the cover art.

    Quantizes to a small palette, then prefers colors with high
    chroma (saturation × value). Falls back to a neutral indigo on
    unusable images (monochrome, tiny, errors)."""
    try:
        thumb = image.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR)
        quant = thumb.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        palette = quant.getpalette() or []
        counts = sorted(quant.getcolors() or [], reverse=True)
        best_score = -1.0
        best_rgb = (124, 143, 255)
        for count, idx in counts:
            r = palette[idx * 3 + 0]
            g = palette[idx * 3 + 1]
            b = palette[idx * 3 + 2]
            # Skip near-black and near-white (rarely make good accents).
            mx = max(r, g, b); mn = min(r, g, b)
            if mx < 40 or mn > 220:
                continue
            sat = (mx - mn) / mx if mx else 0
            val = mx / 255.0
            # Score: chroma weighted, mild popularity bias.
            score = (sat * 0.7 + val * 0.3) * (count ** 0.3)
            if score > best_score:
                best_score = score
                best_rgb = (r, g, b)
        # Brighten low-luminance accents so they read on dark scrim.
        r, g, b = best_rgb
        mx = max(r, g, b)
        if mx < 160:
            scale = 180 / max(1, mx)
            best_rgb = (min(255, int(r * scale)), min(255, int(g * scale)), min(255, int(b * scale)))
        return rgb_to_hex(best_rgb)
    except Exception as e:
        logger.debug(f"Accent extraction failed: {e}")
        return "#7c8fff"


def apply_vignette(image: Image.Image, intensity: float = 0.55) -> Image.Image:
    """Composites a radial darken vignette onto a blurred backdrop so foreground
    text remains readable regardless of cover-art brightness. One PIL pass per
    track change — not per frame."""
    try:
        w, h = image.size
        if w < 4 or h < 4:
            return image
        # Build a radial gradient mask: bright at center, dark at corners.
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        max_r = (w * w + h * h) ** 0.5 / 2
        steps = 24
        for i in range(steps, 0, -1):
            t = i / steps
            radius = max_r * t
            shade = int(255 * (1.0 - t) * intensity)
            cx, cy = w / 2, h / 2
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=shade,
            )
        mask = mask.filter(ImageFilter.GaussianBlur(max(8, min(w, h) // 18)))
        dark = Image.new("RGB", (w, h), (0, 0, 0))
        return Image.composite(dark, image, mask)
    except Exception as e:
        logger.debug(f"Vignette failed: {e}")
        return image


def build_ken_burns_frames(source_image_path: Path, width: int, height: int,
                           blur_strength: int, vignette_intensity: float) -> Optional[Tuple[Image.Image, Image.Image]]:
    """Pre-renders two slightly-different zoom/translate variants of the
    blurred+vignetted backdrop. Tk crossfades between them."""
    try:
        base = create_blurred_background(source_image_path, width, height, blur_strength)
        if base is None:
            return None
        base = apply_vignette(base, intensity=vignette_intensity)
        a = base.resize((int(width * 1.04), int(height * 1.04)), Image.Resampling.LANCZOS)
        a = a.crop((0, 0, width, height))
        b = base.resize((int(width * 1.10), int(height * 1.10)), Image.Resampling.LANCZOS)
        offset_x = (int(width * 1.10) - width)
        offset_y = (int(height * 1.10) - height)
        b = b.crop((offset_x, offset_y, offset_x + width, offset_y + height))
        return a, b
    except Exception as e:
        logger.debug(f"build_ken_burns_frames failed: {e}")
        return None


def install_ken_burns(image_file_path: Path, width: int, height: int) -> bool:
    """Replaces the static blurred background with two crossfading frames."""
    global ken_burns_frame_a_ref, ken_burns_frame_b_ref
    global ken_burns_item_a, ken_burns_item_b, ken_burns_last_window_size

    gui_cfg = config.get("gui", {})
    if not bool(gui_cfg.get("ken_burns_enabled", True)) or not is_motion_enabled(config):
        return False
    if not canvas or width <= 0 or height <= 0:
        return False

    vignette_intensity = safe_float(gui_cfg.get("vignette_intensity")) or 0.55
    blur_strength = gui_cfg.get("blur_strength", 15)
    frames = build_ken_burns_frames(image_file_path, width, height, blur_strength, vignette_intensity)
    if frames is None:
        return False

    ken_burns_frame_a_ref = ImageTk.PhotoImage(frames[0])
    ken_burns_frame_b_ref = ImageTk.PhotoImage(frames[1])

    try:
        canvas.delete("background")
    except tk.TclError:
        pass

    ken_burns_item_a = canvas.create_image(0, 0, anchor=tk.NW, image=ken_burns_frame_a_ref,
                                            tags=("background", "ken_burns"))
    ken_burns_item_b = canvas.create_image(0, 0, anchor=tk.NW, image=ken_burns_frame_b_ref,
                                            tags=("background", "ken_burns"), state="hidden")
    canvas.tag_lower("background")
    ken_burns_last_window_size = (width, height)
    return True


def tick_ken_burns():
    """24s cycle that crossfades by toggling visibility of frame A vs frame B at midpoint."""
    global ken_burns_job_id, ken_burns_phase, ken_burns_direction
    ken_burns_job_id = None
    if not root or not canvas or not root.winfo_exists():
        return
    if not is_motion_enabled(config) or ken_burns_item_a is None:
        try:
            ken_burns_job_id = root.after(2000, tick_ken_burns)
        except tk.TclError:
            ken_burns_job_id = None
        return
    cycle_seconds = 24.0
    step = (1.0 / cycle_seconds) * 0.5  # 0.5s tick
    ken_burns_phase += step * ken_burns_direction
    if ken_burns_phase >= 1.0:
        ken_burns_phase = 1.0
        ken_burns_direction = -1
    elif ken_burns_phase <= 0.0:
        ken_burns_phase = 0.0
        ken_burns_direction = 1
    try:
        if ken_burns_phase < 0.5:
            canvas.itemconfigure(ken_burns_item_a, state="normal")
            canvas.itemconfigure(ken_burns_item_b, state="hidden")
        else:
            canvas.itemconfigure(ken_burns_item_a, state="hidden")
            canvas.itemconfigure(ken_burns_item_b, state="normal")
    except tk.TclError:
        return
    try:
        ken_burns_job_id = root.after(500, tick_ken_burns)
    except tk.TclError:
        ken_burns_job_id = None


SPLASH_STOPS = [
    (124, 143, 255),    # cool indigo
    (200, 110, 180),    # warm pink
    (140, 200, 230),    # cool sky
]


def build_splash_gradient(width: int, height: int, phase: float = 0.0) -> Image.Image:
    """Three-stop mesh-gradient backdrop for the idle splash. `phase` rotates
    which stops anchor which corners (so consecutive renders shift mood)."""
    try:
        scale = 6  # render small + upscale, much faster than per-pixel at native res
        sw, sh = max(8, width // scale), max(8, height // scale)
        layer = Image.new("RGB", (sw, sh), (10, 10, 12))
        pix = layer.load()
        offset = int(phase) % len(SPLASH_STOPS)
        stops = [SPLASH_STOPS[(i + offset) % len(SPLASH_STOPS)] for i in range(3)]
        centers = [
            (int(sw * 0.25), int(sh * 0.30)),
            (int(sw * 0.78), int(sh * 0.40)),
            (int(sw * 0.50), int(sh * 0.78)),
        ]
        max_r = max(sw, sh) * 0.7
        for cx, cy in centers:
            rgb = stops[centers.index((cx, cy))]
            for y in range(sh):
                for x in range(sw):
                    dx = x - cx; dy = y - cy
                    d = (dx * dx + dy * dy) ** 0.5
                    t = max(0.0, 1.0 - d / max_r)
                    t = t * t * 0.6
                    r0, g0, b0 = pix[x, y]
                    r1, g1, b1 = rgb
                    pix[x, y] = (
                        int(r0 + (r1 - r0) * t),
                        int(g0 + (g1 - g0) * t),
                        int(b0 + (b1 - b0) * t),
                    )
        layer = layer.resize((width, height), Image.Resampling.BILINEAR)
        return layer.filter(ImageFilter.GaussianBlur(max(20, min(width, height) // 12)))
    except Exception as e:
        logger.debug(f"build_splash_gradient failed: {e}")
        return Image.new("RGB", (width, height), (10, 10, 12))


def render_idle_splash(window_width: int, window_height: int) -> None:
    """Paints the idle splash: full-window mesh gradient + centered wordmark."""
    global idle_splash_bg_id, idle_splash_bg_photo_ref, idle_splash_wordmark_id
    if not canvas:
        return
    try:
        gradient = build_splash_gradient(window_width, window_height, phase=0.0)
        idle_splash_bg_photo_ref = ImageTk.PhotoImage(gradient)
        if idle_splash_bg_id:
            try:
                canvas.itemconfigure(idle_splash_bg_id, image=idle_splash_bg_photo_ref)
            except tk.TclError:
                idle_splash_bg_id = None
        if not idle_splash_bg_id:
            idle_splash_bg_id = canvas.create_image(
                0, 0, anchor=tk.NW,
                image=idle_splash_bg_photo_ref,
                tags=("idle_splash",),
            )

        wordmark_size = compute_type_scale(min(window_width, window_height))["wordmark"]
        font_obj = (get_ui_font_family(), wordmark_size, "bold")
        text_x = window_width / 2
        text_y = window_height / 2
        if idle_splash_wordmark_id:
            try:
                canvas.coords(idle_splash_wordmark_id, text_x, text_y)
                canvas.itemconfigure(
                    idle_splash_wordmark_id,
                    text="SongPi",
                    font=font_obj,
                    fill="#ffffff",
                    anchor=tk.CENTER,
                )
            except tk.TclError:
                idle_splash_wordmark_id = None
        if not idle_splash_wordmark_id:
            idle_splash_wordmark_id = canvas.create_text(
                text_x, text_y,
                text="SongPi",
                font=font_obj,
                fill="#ffffff",
                anchor=tk.CENTER,
                tags=("idle_splash", "wordmark"),
            )
        canvas.tag_raise("idle_splash")
        canvas.tag_raise("status_pill")
    except tk.TclError as e:
        logger.debug(f"render_idle_splash failed: {e}")


def hide_idle_splash() -> None:
    """Removes splash items if present."""
    if not canvas:
        return
    try:
        canvas.delete("idle_splash")
    except tk.TclError:
        pass
    global idle_splash_bg_id, idle_splash_bg_photo_ref, idle_splash_wordmark_id
    idle_splash_bg_id = None
    idle_splash_bg_photo_ref = None
    idle_splash_wordmark_id = None


def build_cover_halo(cover_size: int, accent_hex: str, intensity: float) -> Optional[Image.Image]:
    """Returns a PIL RGBA image of a soft accent-colored halo sized 1.18× the
    cover. Used as a glow plate placed behind the cover art."""
    try:
        side = max(8, int(cover_size * 1.18))
        halo = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = ImageDraw.Draw(halo)
        r, g, b = hex_to_rgb(accent_hex)
        alpha = int(255 * max(0.0, min(1.0, intensity)))
        margin = side // 8
        draw.ellipse([margin, margin, side - margin, side - margin],
                     fill=(r, g, b, alpha))
        blur_px = max(8, side // 8)
        return halo.filter(ImageFilter.GaussianBlur(blur_px))
    except Exception as e:
        logger.debug(f"build_cover_halo failed: {e}")
        return None


def render_cover_halo(square_x: float, square_y: float, square_size: int) -> None:
    """Renders (or refreshes) the accent halo behind the cover art."""
    global cover_halo_photo_ref, cover_halo_item_id
    if not canvas:
        return
    intensity = safe_float(config.get("gui", {}).get("accent_halo_intensity")) or 0.35
    halo_image = build_cover_halo(square_size, accent_color_hex, intensity)
    if halo_image is None:
        if cover_halo_item_id:
            try:
                canvas.delete(cover_halo_item_id)
            except tk.TclError:
                pass
            cover_halo_item_id = None
        cover_halo_photo_ref = None
        return
    cover_halo_photo_ref = ImageTk.PhotoImage(halo_image)
    if cover_halo_item_id:
        try:
            canvas.coords(cover_halo_item_id, square_x, square_y)
            canvas.itemconfigure(cover_halo_item_id, image=cover_halo_photo_ref)
        except tk.TclError:
            cover_halo_item_id = None
    if not cover_halo_item_id:
        cover_halo_item_id = canvas.create_image(
            square_x, square_y,
            anchor=tk.CENTER,
            image=cover_halo_photo_ref,
            tags=("background", "cover_halo"),
        )
    try:
        canvas.tag_raise("cover_halo", "background")
        if coverart_item_id:
            canvas.tag_raise(coverart_item_id, "cover_halo")
    except tk.TclError:
        pass


def draw_rounded_rect(canvas_obj: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                      radius: float, fill: str, outline: str = "", tags: Tuple[str, ...] = (),
                      existing_id: Optional[int] = None) -> int:
    """Draws a pill/rounded rectangle on a Tk canvas using polygon smoothing.

    Tk canvas has no native rounded rect; smoothing a polygon with control
    points hugging each corner gives a clean pill shape. Returns the item id."""
    r = max(2, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    if existing_id is not None:
        try:
            canvas_obj.coords(existing_id, *points)
            canvas_obj.itemconfigure(existing_id, fill=fill, outline=outline)
            return existing_id
        except tk.TclError:
            pass
    return canvas_obj.create_polygon(points, fill=fill, outline=outline,
                                     smooth=True, splinesteps=24, tags=tags)


# --- Layout system ---

def detect_layout_breakpoint(width: int, height: int) -> str:
    """Returns 'wide', 'mid', or 'stacked' based on window dimensions per spec §4."""
    if height <= 0:
        return "stacked"
    aspect = width / height
    if width >= 900 and aspect >= 1.2:
        return "wide"
    if width < 900 or aspect < 0.95:
        return "stacked"
    return "mid"


def format_artist_label(value: str, max_chars: int = 40) -> str:
    """Renders the artist label in uppercase. If short enough, inserts hair
    spaces between letters to fake letter-tracking (Tk lacks letter-spacing)."""
    if not value:
        return ""
    upper = value.upper()
    if len(upper) <= max_chars:
        return " ".join(upper)
    return upper


def is_low_power_host() -> bool:
    """Heuristic: Pi 3 (armv7) is the canonical low-power target. Anything
    armv7 with <=4 cores triggers the reduced-motion profile by default."""
    import platform
    machine = platform.machine().lower()
    cpu_count = os.cpu_count() or 1
    return machine.startswith("armv7") and cpu_count <= 4


def is_motion_enabled(cfg: Dict[str, Any]) -> bool:
    """True when full motion (Ken Burns, glow breath, choreography) should run."""
    if bool(cfg.get("gui", {}).get("motion_reduced", False)):
        return False
    return not is_low_power_host()


def should_show_idle_splash(last_match_monotonic: float, now_monotonic: float,
                            has_active_track: bool, cfg: Dict[str, Any]) -> bool:
    """Splash if: enabled, no active track, and >= idle_splash_after_seconds
    have elapsed since any successful match."""
    gui_cfg = cfg.get("gui", {})
    if not bool(gui_cfg.get("idle_splash_enabled", True)):
        return False
    if has_active_track:
        return False
    threshold = safe_float(gui_cfg.get("idle_splash_after_seconds")) or 10.0
    return (now_monotonic - last_match_monotonic) >= threshold


def compute_type_scale(short_edge: int) -> Dict[str, int]:
    """Maps window short-edge px to the responsive type sizes from spec §3."""
    s = max(0, int(short_edge))
    return {
        "title":          int(responsive_clamp(18, s * 0.035, 38)),
        "artist":         int(responsive_clamp(11, s * 0.018, 18)),
        "album":          int(responsive_clamp(10, s * 0.015, 15)),
        "lyric_active":   int(responsive_clamp(22, s * 0.052, 64)),
        "lyric_context":  int(responsive_clamp(13, s * 0.025, 24)),
        "status_pill":    int(responsive_clamp(9,  s * 0.013, 14)),
        "history_title":  int(responsive_clamp(9,  s * 0.013, 13)),
        "history_artist": int(responsive_clamp(8,  s * 0.011, 11)),
        "wordmark":       int(responsive_clamp(28, s * 0.060, 96)),
    }


def create_placeholder_image(path: Path, width: int, height: int, text: str) -> bool:
    """Creates a simple placeholder image with text and saves it."""
    logger.info(f"Creating placeholder image at: {path}")
    try:
        img = Image.new('RGB', (width, height), color = (70, 70, 70))
        d = ImageDraw.Draw(img)
        try:
            font_size = max(15, int(min(width, height) * 0.1))
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                try:
                    font = ImageFont.truetype("verdana.ttf", font_size)
                except IOError:
                    logger.warning("Arial/Verdana not found, using default PIL font.")
                    font = ImageFont.load_default()

            if hasattr(d, 'textbbox'):
                 bbox = d.textbbox((0, 0), text, font=font, anchor="lt")
                 text_width = bbox[2] - bbox[0]
                 text_height = bbox[3] - bbox[1]
            else:
                 text_width, text_height = d.textsize(text, font=font)

            text_x = (width - text_width) / 2
            text_y = (height - text_height) / 2
            d.text((text_x, text_y), text, fill=(200, 200, 200), font=font)
        except Exception as font_e:
            logger.error(f"Error during text drawing on placeholder: {font_e}")
            pass
        img.save(path)
        logger.info(f"Placeholder saved.")
        return True
    except Exception as e:
        logger.error(f"Failed to create placeholder image {path}: {e}")
        return False


# --- History Management ---
def safe_remove(path: Optional[Union[str, Path]], description: str = "file") -> bool:
    """Safely remove a file or path, logging errors. Returns True if removed, False otherwise."""
    if path:
        path_obj = Path(path)
        if path_obj.is_file():
            try:
                path_obj.unlink()
                logger.debug(f"Removed {description}: {path_obj}")
                return True
            except OSError as e:
                logger.error(f"Error removing {description} {path_obj}: {e}")
                return False
    return False

def serialize_history_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Converts a history entry into a JSON-safe dict."""
    timestamp = entry.get('timestamp')
    if isinstance(timestamp, datetime):
        timestamp = timestamp.isoformat()
    elif timestamp is None:
        timestamp = ""

    return {
        'title': str(entry.get('title', '')).strip(),
        'artist': str(entry.get('artist', '')).strip(),
        'album': str(entry.get('album', '')).strip(),
        'image_path': str(entry.get('image_path', '')).strip(),
        'timestamp': str(timestamp).strip(),
    }

def save_history_state():
    """Persists the in-memory history list so cinematic history survives restarts."""
    if not config:
        return

    max_mem_items = max(1, int(config['gui'].get('history_max_items', 5))) + 1
    state_entries: List[Dict[str, Any]] = []

    for entry in song_history_list[:max_mem_items]:
        serialized = serialize_history_entry(entry)
        image_path = serialized.get('image_path')
        if not serialized['title'] or not serialized['artist'] or not image_path:
            continue
        if not Path(image_path).is_file():
            continue
        state_entries.append(serialized)

    try:
        with open(HISTORY_STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump({'entries': state_entries}, f, indent=4)
        logger.debug(f"Saved history state to {HISTORY_STATE_FILE_PATH}")
    except IOError as e:
        logger.error(f"Failed to save history state to {HISTORY_STATE_FILE_PATH}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error saving history state: {e}")

def rebuild_history_state_from_legacy_assets() -> List[Dict[str, Any]]:
    """Best-effort migration for users who already have history images/logs but no JSON state."""
    if not HISTORY_IMAGE_DIR_PATH.is_dir():
        return []

    image_files = sorted(
        (p for p in HISTORY_IMAGE_DIR_PATH.glob('*.jpg') if p.is_file()),
        key=lambda p: p.name,
        reverse=True
    )
    if not image_files:
        return []

    parsed_log_entries: List[Dict[str, Any]] = []
    if SONG_HISTORY_FILE_PATH.is_file():
        try:
            with open(SONG_HISTORY_FILE_PATH, 'r', encoding='utf-8') as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith('---') or ' | ' not in line:
                        continue
                    timestamp_text, _, song_text = line.partition(' | ')
                    if ' - ' not in song_text:
                        continue
                    artist_text, title_text = song_text.split(' - ', 1)
                    parsed_log_entries.append({
                        'title': title_text.strip(),
                        'artist': artist_text.strip(),
                        'album': '',
                        'timestamp': timestamp_text.strip(),
                    })
        except Exception as e:
            logger.warning(f"Could not parse legacy history log {SONG_HISTORY_FILE_PATH}: {e}")

    parsed_log_entries.reverse()
    migrated_entries: List[Dict[str, Any]] = []
    for index, image_path in enumerate(image_files):
        fallback_title = image_path.stem.split('_', 2)[-1].replace('_', ' ').strip()
        fallback_title = fallback_title or "Unknown Title"
        base_entry = parsed_log_entries[index] if index < len(parsed_log_entries) else {
            'title': fallback_title,
            'artist': 'Unknown Artist',
            'album': '',
            'timestamp': '',
        }
        migrated_entries.append({
            'title': base_entry.get('title') or fallback_title,
            'artist': base_entry.get('artist') or 'Unknown Artist',
            'album': base_entry.get('album') or '',
            'image_path': str(image_path),
            'timestamp': base_entry.get('timestamp') or '',
        })

    if migrated_entries:
        logger.info(f"Recovered {len(migrated_entries)} history items from legacy assets.")
    return migrated_entries

def load_history_state():
    """Loads recent history entries so the cinematic stack survives app restarts."""
    global song_history_list
    song_history_list = []

    raw_entries: List[Dict[str, Any]] = []
    loaded_from_state_file = False

    if HISTORY_STATE_FILE_PATH.is_file():
        try:
            with open(HISTORY_STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                raw_entries = payload.get('entries') or []
            elif isinstance(payload, list):
                raw_entries = payload
            loaded_from_state_file = True
        except Exception as e:
            logger.warning(f"Could not load history state from {HISTORY_STATE_FILE_PATH}: {e}")

    if not raw_entries:
        raw_entries = rebuild_history_state_from_legacy_assets()

    max_mem_items = max(1, int(config['gui'].get('history_max_items', 5))) + 1
    normalized_entries: List[Dict[str, Any]] = []

    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        serialized = serialize_history_entry(entry)
        image_path = serialized.get('image_path')
        if not serialized['title'] or not serialized['artist'] or not image_path:
            continue
        if not Path(image_path).is_file():
            continue
        normalized_entries.append(serialized)
        if len(normalized_entries) >= max_mem_items:
            break

    song_history_list = normalized_entries

    if song_history_list:
        logger.info(f"Loaded {len(song_history_list)} history items into memory.")
        if not loaded_from_state_file or len(song_history_list) != len(raw_entries[:max_mem_items]):
            save_history_state()
    else:
        logger.info("No persisted history items were available to restore.")

def add_to_history(track_title: str, artist_name: str, album_name: Optional[str], source_image_path: Path) -> Optional[str]:
    """Adds song to history, copies art, manages list size, logs to file, returns persistent path."""
    global song_history_list
    if song_history_list and song_history_list[0]['title'] == track_title and song_history_list[0]['artist'] == artist_name:
        logger.debug("Skipping adding duplicate song to history (same as last).")
        return song_history_list[0]['image_path']

    timestamp = datetime.now()
    safe_title = "".join(c for c in track_title if c.isalnum() or c in (' ', '_')).rstrip()[:30].replace(' ', '_')
    history_filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{safe_title}.jpg"
    persistent_image_path_obj = HISTORY_IMAGE_DIR_PATH / history_filename
    persistent_image_path_str = str(persistent_image_path_obj)

    try:
        if not source_image_path.is_file():
            logger.error(f"Source for history copy does not exist: {source_image_path}")
            return None

        HISTORY_IMAGE_DIR_PATH.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image_path, persistent_image_path_obj)
        logger.info(f"Copied cover art to history: {persistent_image_path_obj}")

        history_entry = {
            'title': track_title,
            'artist': artist_name,
            'album': album_name or "",
            'image_path': persistent_image_path_str,
            'timestamp': timestamp
        }
        song_history_list.insert(0, history_entry)

        max_mem_items = config['gui']['history_max_items'] + 1
        if len(song_history_list) > max_mem_items:
            song_history_list = song_history_list[:max_mem_items]
            logger.debug(f"Pruned in-memory history list to {max_mem_items} items.")

        save_history_state()

        try:
            log_timestamp = timestamp.strftime('%Y-%m-%d %H:%M')
            log_line = f"{log_timestamp} | {artist_name} - {track_title}\n"
            with open(SONG_HISTORY_FILE_PATH, 'a', encoding='utf-8') as f:
                f.write(log_line)
            logger.debug(f"Logged song to history file: {SONG_HISTORY_FILE_PATH}")
        except IOError as e:
            logger.error(f"Failed to write to song history file {SONG_HISTORY_FILE_PATH}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error writing to history log file: {e}")

        return persistent_image_path_str

    except FileNotFoundError:
        logger.error(f"Source not found during history copy: {source_image_path}")
        return None
    except OSError as e:
        logger.error(f"OS error during history image copy or directory creation: {e}")
        safe_remove(persistent_image_path_obj, "history image on OS error")
        return None
    except Exception as e:
        logger.exception(f"Error adding song to history/copying image {source_image_path}: {e}")
        safe_remove(persistent_image_path_obj, "history image on error")
        return None

def cleanup_old_history_images(keep_count: int = 20):
    """Removes oldest history images based on filename timestamp, keeping the specified number."""
    global song_history_list
    logger.info(f"Running history cleanup, aiming to keep newest {keep_count} images based on filename.")
    if not HISTORY_IMAGE_DIR_PATH.is_dir():
        logger.warning(f"History image directory not found: {HISTORY_IMAGE_DIR_PATH}. Skipping cleanup.")
        return

    try:
        history_files = [
            p for p in HISTORY_IMAGE_DIR_PATH.glob('*.jpg') if p.is_file()
        ]
        history_files.sort(key=lambda p: p.name, reverse=True)

        if len(history_files) > keep_count:
            files_to_remove = history_files[keep_count:]
            logger.info(f"Found {len(history_files)} history images. Removing {len(files_to_remove)} oldest ones.")
            removed_count = 0
            for file_path in files_to_remove:
                if safe_remove(file_path, "old history image during cleanup"):
                    removed_count += 1
            if removed_count:
                song_history_list = [
                    entry for entry in song_history_list
                    if Path(str(entry.get('image_path', ''))).is_file()
                ]
                save_history_state()
            logger.info(f"History cleanup finished. Successfully removed {removed_count} images.")
        else:
            logger.info(f"Found {len(history_files)} history images. No cleanup needed (Keep count: {keep_count}).")

    except OSError as e:
        logger.error(f"OS Error during history cleanup scan in {HISTORY_IMAGE_DIR_PATH}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during history image cleanup: {e}")


# --- State Persistence ---
def save_last_state(title: str, artist: str, album: str, persistent_image_path: Optional[str]):
    """Saves the last successfully identified song details."""
    state = {
        'title': title,
        'artist': artist,
        'album': album,
        'persistent_image_path': persistent_image_path,
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(LAST_STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)
        logger.info(f"Saved last state to {LAST_STATE_FILE_PATH}")
    except IOError as e:
        logger.error(f"Failed to save last state to {LAST_STATE_FILE_PATH}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error saving last state: {e}")

def load_last_state() -> bool:
    """Loads the last state if available and valid."""
    global last_track_title, last_album_name, last_artist_name, last_persistent_image_path, current_status_message
    if not LAST_STATE_FILE_PATH.is_file():
        logger.info("No previous state file found.")
        return False
    try:
        logger.info(f"Loading last state from: {LAST_STATE_FILE_PATH}")
        with open(LAST_STATE_FILE_PATH, 'r', encoding='utf-8') as f:
            state = json.load(f)

        required_keys = ['title', 'artist']
        if not all(key in state for key in required_keys):
            logger.warning("Last state file missing required keys (title, artist). Discarding.")
            safe_remove(LAST_STATE_FILE_PATH, "invalid last state file")
            return False

        last_track_title = state.get('title', 'Unknown Title')
        last_album_name = state.get('album', '')
        last_artist_name = state.get('artist', 'Unknown Artist')
        logger.info(f"Restored last known song text: '{last_track_title}' by {last_artist_name}")
        text_loaded = True

        image_restored = False
        img_path_str = state.get('persistent_image_path')
        if img_path_str:
            img_path = Path(img_path_str)
            if img_path.is_file():
                try:
                    shutil.copy2(img_path, IMAGE_PATH)
                    logger.info(f"Restored active image '{IMAGE_PATH}' from persistent state: {img_path}")
                    last_persistent_image_path = img_path_str
                    image_restored = True
                except Exception as e:
                    logger.error(f"Failed to copy image from last state {img_path} to {IMAGE_PATH}: {e}")
                    safe_remove(IMAGE_PATH, "failed restore image copy")
                    last_persistent_image_path = None
            else:
                logger.warning(f"Image path in last state file not found: {img_path}. Active image may be missing.")
                last_persistent_image_path = None
        else:
             logger.info("Persistent image path null/missing in last state file. Active image may be missing.")
             last_persistent_image_path = None

        if not IMAGE_PATH.is_file():
            create_placeholder_image(IMAGE_PATH, 300, 300, "Image Unavailable")

        if text_loaded:
            if image_restored:
                 schedule_gui_update(set_status_message, "Ready (Restored)")
            else:
                 schedule_gui_update(set_status_message, "Ready (Restored Text Only)")
            return True
        else:
            return False

    except json.JSONDecodeError:
        logger.error(f"Error decoding last state file: {LAST_STATE_FILE_PATH}. Discarding.")
        safe_remove(LAST_STATE_FILE_PATH, "corrupted last state file")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error loading last state: {e}")
        return False


# --- Lyrics Handling ---
def normalize_lyrics_key_part(value: Optional[str]) -> str:
    """Normalizes artist/title values for cache and scoring."""
    if not value:
        return ""
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9 ]", "", normalized)
    return normalized


def build_track_key(title: str, artist: str) -> str:
    """Creates a stable track key for current-song state."""
    return f"{normalize_lyrics_key_part(artist)}::{normalize_lyrics_key_part(title)}"


def safe_float(value: Any) -> Optional[float]:
    """Converts loosely typed numeric values into floats."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def responsive_clamp(min_value: float, value: float, max_value: float) -> float:
    """CSS-style clamp(lo, val, hi). Used throughout the responsive type/spacing scale."""
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out: fast start, gentle landing. Domain and range [0, 1]."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def fit_canvas_title_font(
    canvas_obj: tk.Canvas,
    text_item_id: Optional[int],
    text: str,
    x_pos: float,
    y_pos: float,
    width: int,
    fill: str,
    anchor: str,
    justify: str,
    base_size: int,
    min_size: int,
    max_height: int,
    family: Optional[str] = None,
    weight: str = "bold",
    slant: str = "roman",
    tags: Tuple[str, ...] = ("main_text",),
) -> Tuple[int, tkFont.Font, Tuple[int, int, int, int]]:
    """Shrinks the current-song title font until its wrapped height fits the allotted block."""
    if family is None:
        family = get_ui_font_family()
    font_size = max(min_size, base_size)
    item_id = text_item_id
    fallback_bbox = (int(x_pos), int(y_pos), int(x_pos + width), int(y_pos + max_height))
    last_font_obj: Optional[tkFont.Font] = None
    last_bbox: Optional[Tuple[int, int, int, int]] = None

    while font_size >= min_size:
        font_obj = tkFont.Font(family=family, size=font_size, weight=weight, slant=slant)
        if item_id:
            canvas_obj.coords(item_id, x_pos, y_pos)
            canvas_obj.itemconfigure(
                item_id,
                text=text,
                font=font_obj,
                fill=fill,
                anchor=anchor,
                justify=justify,
                width=width,
                tags=tags,
            )
        else:
            item_id = canvas_obj.create_text(
                x_pos,
                y_pos,
                text=text,
                font=font_obj,
                fill=fill,
                anchor=anchor,
                justify=justify,
                width=width,
                tags=tags,
            )

        bbox = canvas_obj.bbox(item_id)
        last_font_obj = font_obj
        last_bbox = bbox if bbox else fallback_bbox
        if bbox and (bbox[3] - bbox[1]) <= max_height:
            return item_id, font_obj, bbox
        font_size -= 1

    if not item_id or not last_font_obj:
        raise tk.TclError("Failed to create dynamic title text item.")
    return item_id, last_font_obj, last_bbox or fallback_bbox


def extract_track_duration_seconds(track_info: Dict[str, Any]) -> Optional[float]:
    """Pulls a usable duration value from several common track payload shapes."""
    candidates = [
        track_info.get("duration"),
        track_info.get("duration_sec"),
        track_info.get("length"),
        track_info.get("lengthSeconds"),
    ]

    hub = track_info.get("hub")
    if isinstance(hub, dict):
        for action in hub.get("actions", []):
            if not isinstance(action, dict):
                continue
            candidates.extend([
                action.get("duration"),
                action.get("duration_sec"),
                action.get("length"),
            ])

    for candidate in candidates:
        parsed = safe_float(candidate)
        if parsed and parsed > 0:
            return parsed
    return None


def extract_match_offset_seconds(result: Dict[str, Any]) -> float:
    """Returns the song-position (seconds) corresponding to the start of the
    captured audio sample, as reported by Shazam.

    Note: this is *not* the current playback position. Callers must add the
    elapsed wall-clock time between capture start and 'now' to estimate the
    live song position.
    """
    offset_seconds = 0.0
    matches = result.get("matches", [])
    if matches and isinstance(matches[0], dict):
        offset_value = safe_float(matches[0].get("offset"))
        if offset_value is not None:
            offset_seconds = max(0.0, offset_value)
    return offset_seconds


def parse_lrc_timestamp(timestamp: str) -> Optional[float]:
    """Parses an LRC timestamp such as 01:23.45 into seconds."""
    match = re.match(r"^(?P<minutes>\d+):(?P<seconds>\d{2}(?:\.\d+)?)$", timestamp.strip())
    if not match:
        return None
    minutes = int(match.group("minutes"))
    seconds = float(match.group("seconds"))
    return (minutes * 60) + seconds


def parse_lrc_offset_tag(lrc_text: str) -> float:
    """Extracts an LRC [offset:+ms] tag (milliseconds) as seconds.

    Per LRC convention, a positive offset means lyrics should appear earlier
    relative to the song clock; we return the value to *subtract* from the
    playback position so that a positive tag pulls displayed lines forward.
    """
    match = re.search(r"\[offset:\s*([+-]?\d+)\s*\]", lrc_text, flags=re.IGNORECASE)
    if not match:
        return 0.0
    try:
        return int(match.group(1)) / 1000.0
    except ValueError:
        return 0.0


def parse_synced_lyrics(lrc_text: str) -> List[Dict[str, Any]]:
    """Converts LRCLIB synced lyrics into sorted timestamp/text rows."""
    parsed_lines: List[Dict[str, Any]] = []
    for raw_line in lrc_text.splitlines():
        timestamps = re.findall(r"\[([0-9]{1,2}:\d{2}(?:\.\d{1,3})?)\]", raw_line)
        lyric_text = re.sub(r"\[[^\]]+\]", "", raw_line).strip()
        if not timestamps:
            continue
        for timestamp in timestamps:
            seconds = parse_lrc_timestamp(timestamp)
            if seconds is None:
                continue
            parsed_lines.append({
                "time_seconds": seconds,
                "text": lyric_text if lyric_text else "..."
            })

    parsed_lines.sort(key=lambda item: item["time_seconds"])
    return parsed_lines


def pick_best_lyrics_candidate(candidates: List[Dict[str, Any]], title: str, artist: str) -> Optional[Dict[str, Any]]:
    """Selects the best LRCLIB candidate using title/artist similarity and synced preference."""
    normalized_title = normalize_lyrics_key_part(title)
    normalized_artist = normalize_lyrics_key_part(artist)
    best_candidate = None
    best_score = -1

    for candidate in candidates:
        candidate_title = normalize_lyrics_key_part(
            candidate.get("trackName") or candidate.get("name") or candidate.get("title")
        )
        candidate_artist = normalize_lyrics_key_part(
            candidate.get("artistName") or candidate.get("artist") or candidate.get("artist_name")
        )

        score = 0
        if candidate_title == normalized_title:
            score += 4
        elif normalized_title and normalized_title in candidate_title:
            score += 2

        if candidate_artist == normalized_artist:
            score += 4
        elif normalized_artist and normalized_artist in candidate_artist:
            score += 2

        if candidate.get("syncedLyrics"):
            score += 3
        elif candidate.get("plainLyrics"):
            score += 1

        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate


_TITLE_SUFFIX_PATTERNS = [
    r"\s*[-–—]\s*(?:remastered|remaster|re-?recorded|re-?master|radio edit|single version|album version|mono|stereo|deluxe|expanded|bonus track|live|acoustic|instrumental|extended mix|club mix|edit|version)\b.*$",
    r"\s*\((?:feat\.?|featuring|ft\.?|with)\s[^)]*\)",
    r"\s*\[(?:feat\.?|featuring|ft\.?|with)\s[^\]]*\]",
    r"\s*\((?:official|lyric|lyrics|audio|video|music video|visualizer|hd|4k)[^)]*\)",
    r"\s*\[(?:official|lyric|lyrics|audio|video|music video|visualizer|hd|4k)[^\]]*\]",
    r"\s*\((?:from|from the)\s[^)]*\)",
    r"\s*[-–—]\s*from\s+[\"“‘].*$",
]
_ARTIST_FEAT_PATTERN = re.compile(
    r"\s*(?:feat\.?|featuring|ft\.?|with|,|&|x|×|\+|/)\s.*$",
    flags=re.IGNORECASE,
)


def normalize_search_text(value: Optional[str]) -> str:
    """Looser normalization for *search queries* (kept human-readable)."""
    if not value:
        return ""
    # Unicode-fold accents and smart quotes.
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.replace("‘", "'").replace("’", "'")
    folded = folded.replace("“", '"').replace("”", '"')
    folded = folded.replace("&", " and ")
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded


def clean_title_variants(title: str) -> List[str]:
    """Returns title variants in order: original, deparenthesized, stripped-features-and-suffixes."""
    variants: List[str] = []
    base = normalize_search_text(title)
    if base:
        variants.append(base)

    stripped = base
    for pattern in _TITLE_SUFFIX_PATTERNS:
        stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -–—:,")
    if stripped and stripped != base:
        variants.append(stripped)

    bare = re.sub(r"[\(\[].*?[\)\]]", "", base)
    bare = re.sub(r"\s+", " ", bare).strip(" -–—:,")
    if bare and bare not in variants:
        variants.append(bare)

    return variants


def clean_artist_variants(artist: str) -> List[str]:
    """Returns artist variants: full, primary-only (strip feat/with/&)."""
    variants: List[str] = []
    base = normalize_search_text(artist)
    if base:
        variants.append(base)
    primary = _ARTIST_FEAT_PATTERN.sub("", base).strip()
    if primary and primary != base:
        variants.append(primary)
    return variants


def cache_key(title: str, artist: str) -> str:
    return build_track_key(title, artist)


def load_lyrics_cache() -> Dict[str, Any]:
    if not LYRICS_CACHE_FILE_PATH.is_file():
        return {}
    try:
        with open(LYRICS_CACHE_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load lyrics cache: {e}")
    return {}


def save_lyrics_cache() -> None:
    try:
        with open(LYRICS_CACHE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(lyrics_cache, f, ensure_ascii=False)
    except OSError as e:
        logger.warning(f"Could not save lyrics cache: {e}")


def cache_lookup(title: str, artist: str) -> Optional[Dict[str, Any]]:
    cache_cfg = config.get("lyrics", {})
    ttl_hit = max(0, int(safe_float(cache_cfg.get("cache_ttl_hours")) or 720))   # 30d
    ttl_miss = max(0, int(safe_float(cache_cfg.get("cache_miss_ttl_hours")) or 24))
    entry = lyrics_cache.get(cache_key(title, artist))
    if not isinstance(entry, dict):
        return None
    fetched_at = safe_float(entry.get("fetched_at")) or 0.0
    age_hours = (time.time() - fetched_at) / 3600.0
    is_miss = not (entry.get("syncedLyrics") or entry.get("plainLyrics"))
    ttl = ttl_miss if is_miss else ttl_hit
    if ttl and age_hours > ttl:
        return None
    return entry


def cache_store(title: str, artist: str, candidate: Optional[Dict[str, Any]]) -> None:
    payload = dict(candidate) if candidate else {}
    payload["fetched_at"] = time.time()
    lyrics_cache[cache_key(title, artist)] = payload
    save_lyrics_cache()


def is_acceptable_candidate(candidate: Optional[Dict[str, Any]], prefer_synced: bool) -> bool:
    if not candidate:
        return False
    if candidate.get("syncedLyrics"):
        return True
    if not prefer_synced and candidate.get("plainLyrics"):
        return True
    return False


def _lyrics_http_get(url: str, params: Dict[str, Any], headers: Dict[str, str],
                     timeout: int, attempts: int = 2) -> Optional[requests.Response]:
    """HTTP GET with one retry on timeout / connection error. Lyric APIs are
    slow on cold TLS handshakes, so we don't want a single timeout to nuke
    the whole fetch ladder."""
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, attempts)):
        try:
            return requests.get(url, params=params, headers=headers, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            logger.debug(f"Lyric HTTP {url} attempt {attempt + 1} timed out: {e}")
            continue
        except requests.RequestException as e:
            logger.debug(f"Lyric HTTP {url} failed: {e}")
            return None
    if last_exc is not None:
        logger.debug(f"Lyric HTTP {url} exhausted retries: {last_exc}")
    return None


def lrclib_get(title: str, artist: str, album: Optional[str], duration: Optional[float],
               timeout: int, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    params: Dict[str, Any] = {"track_name": title, "artist_name": artist}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = int(duration)
    response = _lyrics_http_get("https://lrclib.net/api/get", params, headers, timeout)
    if response is None or not response.ok:
        return None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except ValueError as e:
        logger.debug(f"LRCLIB /get bad JSON: {e}")
    return None


def lrclib_search(title: str, artist: str, timeout: int, headers: Dict[str, str],
                  duration: Optional[float] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"track_name": title, "artist_name": artist}
    response = _lyrics_http_get("https://lrclib.net/api/search", params, headers, timeout)
    if response is None or not response.ok:
        # Try the looser `q=` parameter as a fallback — LRCLIB sometimes
        # returns better hits for messy titles via free-text search.
        response = _lyrics_http_get(
            "https://lrclib.net/api/search",
            {"q": f"{title} {artist}".strip()},
            headers,
            timeout,
        )
    if response is None or not response.ok:
        return []
    try:
        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
    except ValueError as e:
        logger.debug(f"LRCLIB /search bad JSON: {e}")
    return []


def score_lrclib_candidate(candidate: Dict[str, Any], title: str, artist: str,
                           duration: Optional[float]) -> int:
    norm_title = normalize_lyrics_key_part(title)
    norm_artist = normalize_lyrics_key_part(artist)
    cand_title = normalize_lyrics_key_part(
        candidate.get("trackName") or candidate.get("name") or candidate.get("title")
    )
    cand_artist = normalize_lyrics_key_part(
        candidate.get("artistName") or candidate.get("artist") or candidate.get("artist_name")
    )
    score = 0
    if cand_title == norm_title:
        score += 6
    elif norm_title and norm_title in cand_title:
        score += 3
    elif cand_title and cand_title in norm_title:
        score += 2

    if cand_artist == norm_artist:
        score += 6
    elif norm_artist and norm_artist in cand_artist:
        score += 3
    elif cand_artist and cand_artist in norm_artist:
        score += 2

    if candidate.get("syncedLyrics"):
        score += 5
    elif candidate.get("plainLyrics"):
        score += 1

    cand_duration = safe_float(candidate.get("duration"))
    if duration and cand_duration:
        diff = abs(cand_duration - duration)
        if diff <= 2:
            score += 4
        elif diff <= 5:
            score += 2
        elif diff > 15:
            score -= 3
    return score


def pick_best_scored_candidate(candidates: List[Dict[str, Any]], title: str, artist: str,
                               duration: Optional[float]) -> Optional[Dict[str, Any]]:
    best = None
    best_score = -1
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        s = score_lrclib_candidate(cand, title, artist, duration)
        if s > best_score:
            best_score = s
            best = cand
    return best


def netease_fallback(title: str, artist: str, timeout: int, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Searches NetEase Cloud Music (public unofficial endpoints) as a secondary
    timed-lyric source. Tries the community-mirror search → lyric API.
    Returns a candidate shaped like the LRCLIB payload so the rest of the pipeline
    is unchanged."""
    base = config.get("lyrics", {}).get("netease_api_base", "https://music.xianqiao.wang/neteaseapiv2")
    base = base.rstrip("/")
    keywords = f"{title} {artist}".strip()
    try:
        search_resp = requests.get(
            f"{base}/search",
            params={"keywords": keywords, "limit": 10, "type": 1},
            headers=headers,
            timeout=timeout,
        )
        search_resp.raise_for_status()
        search_payload = search_resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.debug(f"NetEase search failed for '{title}'/'{artist}': {e}")
        return None

    songs = (
        search_payload.get("result", {}).get("songs")
        if isinstance(search_payload, dict)
        else None
    ) or []
    if not isinstance(songs, list) or not songs:
        return None

    norm_title = normalize_lyrics_key_part(title)
    norm_artist = normalize_lyrics_key_part(artist)
    best_song = None
    best_score = -1
    for song in songs:
        if not isinstance(song, dict):
            continue
        sname = normalize_lyrics_key_part(song.get("name"))
        artists = song.get("artists") or song.get("ar") or []
        anames = " ".join(
            normalize_lyrics_key_part(a.get("name")) for a in artists if isinstance(a, dict)
        )
        s = 0
        if sname == norm_title:
            s += 6
        elif norm_title and norm_title in sname:
            s += 3
        if norm_artist and norm_artist in anames:
            s += 4
        if s > best_score:
            best_score = s
            best_song = song

    if not best_song or best_score < 4:
        return None

    song_id = best_song.get("id")
    if not song_id:
        return None

    try:
        lyric_resp = requests.get(
            f"{base}/lyric",
            params={"id": song_id},
            headers=headers,
            timeout=timeout,
        )
        lyric_resp.raise_for_status()
        lyric_payload = lyric_resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.debug(f"NetEase lyric fetch failed for id={song_id}: {e}")
        return None

    if not isinstance(lyric_payload, dict):
        return None
    lrc = (lyric_payload.get("lrc") or {}).get("lyric") or ""
    if not lrc.strip():
        return None

    # Quick check: LRC must contain at least one timestamp tag to count as synced.
    if not re.search(r"\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", lrc):
        return None

    artists = best_song.get("artists") or best_song.get("ar") or []
    artist_name = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict)).strip(", ")
    return {
        "trackName": best_song.get("name"),
        "artistName": artist_name or artist,
        "syncedLyrics": lrc,
        "plainLyrics": "",
        "duration": (best_song.get("duration") or 0) / 1000.0 or None,
        "source": "netease",
    }


def request_lrclib_candidate(title: str, artist: str, album: Optional[str], duration: Optional[float]) -> Optional[Dict[str, Any]]:
    """Multi-strategy lyric fetch: cache → LRCLIB search across variants → NetEase fallback.

    We lead with /search rather than /get because /search is fuzzy, returns
    multiple ranked candidates we can score, and tolerates Shazam metadata
    quirks (punctuation, feat. tags, mismatched album/duration)."""
    lyrics_cfg = config.get("lyrics", {})
    base_timeout = config["network"]["timeout"]
    fetch_timeout = max(base_timeout, int(safe_float(lyrics_cfg.get("fetch_timeout_seconds")) or 15))
    headers = {"User-Agent": "SongPi/1.2 (https://github.com/kyol-dony/SongPi)"}
    prefer_synced = bool(lyrics_cfg.get("prefer_synced_lyrics", True))
    enable_netease = bool(lyrics_cfg.get("enable_netease_fallback", True))

    cached = cache_lookup(title, artist)
    if cached is not None:
        if is_acceptable_candidate(cached, prefer_synced):
            logger.debug(f"Lyrics cache hit for '{title}' by '{artist}'.")
            return cached
        if not cached.get("syncedLyrics") and not cached.get("plainLyrics"):
            logger.debug(f"Lyrics cache: previous miss still fresh for '{title}' by '{artist}'.")
            return None

    title_variants = clean_title_variants(title) or [title]
    artist_variants = clean_artist_variants(artist) or [artist]
    album_clean = normalize_search_text(album) if album else None

    best_candidate: Optional[Dict[str, Any]] = None

    def consider(cand: Optional[Dict[str, Any]]):
        nonlocal best_candidate
        if not cand:
            return
        if best_candidate is None:
            best_candidate = cand
            return
        new_score = score_lrclib_candidate(cand, title, artist, duration)
        cur_score = score_lrclib_candidate(best_candidate, title, artist, duration)
        if new_score > cur_score:
            best_candidate = cand

    # Step 1: a single tight /get attempt with full metadata — if it lands we
    # save ~one round-trip. Skip if no album/duration to avoid a guaranteed 404.
    if album_clean and duration:
        consider(lrclib_get(title_variants[0], artist_variants[0], album_clean, duration, fetch_timeout, headers))

    # Step 2: /search across (title × artist) variants, then score everything.
    if not is_acceptable_candidate(best_candidate, prefer_synced):
        seen_keys = set()
        all_search_results: List[Dict[str, Any]] = []
        for t in title_variants:
            for a in artist_variants:
                key = (t.lower(), a.lower())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                results = lrclib_search(t, a, fetch_timeout, headers, duration)
                all_search_results.extend(results)
                if len(all_search_results) >= 30:
                    break
            if len(all_search_results) >= 30:
                break
        scored = pick_best_scored_candidate(all_search_results, title, artist, duration)
        consider(scored)

    # Step 3: NetEase fallback for tracks LRCLIB doesn't carry.
    if enable_netease and not is_acceptable_candidate(best_candidate, prefer_synced):
        netease_cand = netease_fallback(title_variants[0], artist_variants[0], fetch_timeout, headers)
        consider(netease_cand)

    cache_store(title, artist, best_candidate)
    return best_candidate


def set_lyrics_state(
    track_key: str,
    synced_lines: List[Dict[str, Any]],
    plain_lyrics: str,
    anchor_song_seconds: float,
    anchor_monotonic: float,
    lrc_offset_seconds: float,
    source: Optional[str],
) -> None:
    """Stores current lyrics state for the active song.

    `anchor_song_seconds` is the song-position (s) at `anchor_monotonic`
    (a time.monotonic() value). Live position = anchor_song_seconds +
    (time.monotonic() - anchor_monotonic) - lrc_offset_seconds + user_adjust.
    """
    lyrics_state["track_key"] = track_key
    lyrics_state["source"] = source
    lyrics_state["synced_lines"] = synced_lines
    lyrics_state["plain_lyrics"] = plain_lyrics.strip()
    lyrics_state["display_lines"] = []
    lyrics_state["anchor_monotonic"] = anchor_monotonic
    lyrics_state["anchor_song_seconds"] = anchor_song_seconds
    lyrics_state["lrc_offset_seconds"] = lrc_offset_seconds


def clear_lyrics_state() -> None:
    """Clears all currently displayed lyrics."""
    lyrics_state["track_key"] = None
    lyrics_state["source"] = None
    lyrics_state["synced_lines"] = []
    lyrics_state["plain_lyrics"] = ""
    lyrics_state["display_lines"] = []
    lyrics_state["anchor_monotonic"] = None
    lyrics_state["anchor_song_seconds"] = 0.0
    lyrics_state["lrc_offset_seconds"] = 0.0


def refine_lyrics_anchor(candidate_song_seconds: float, candidate_monotonic: float) -> None:
    """Blends a new recognition's anchor into the existing one for the same
    track using an exponential moving average. Keeps lyrics from snapping
    backwards on every cycle while still correcting drift."""
    existing_anchor_monotonic = lyrics_state.get("anchor_monotonic")
    existing_anchor_song = lyrics_state.get("anchor_song_seconds", 0.0)
    if existing_anchor_monotonic is None:
        lyrics_state["anchor_monotonic"] = candidate_monotonic
        lyrics_state["anchor_song_seconds"] = candidate_song_seconds
        return

    expected_at_candidate = existing_anchor_song + (candidate_monotonic - existing_anchor_monotonic)
    delta = candidate_song_seconds - expected_at_candidate

    # Sanity: ignore wild outliers (likely Shazam mis-match), hard reset on big shifts (track change missed).
    if abs(delta) > 30.0:
        lyrics_state["anchor_monotonic"] = candidate_monotonic
        lyrics_state["anchor_song_seconds"] = candidate_song_seconds
        return
    if abs(delta) < 0.2:
        return

    alpha = safe_float(config.get("lyrics", {}).get("anchor_smoothing_alpha")) or 0.35
    alpha = min(1.0, max(0.05, alpha))
    lyrics_state["anchor_song_seconds"] = existing_anchor_song + delta * alpha


def extract_album_name(track_info: Dict[str, Any]) -> Optional[str]:
    """Best-effort album extraction from Shazam metadata."""
    sections = track_info.get("sections", [])
    if not isinstance(sections, list):
        return None

    for section in sections:
        if not isinstance(section, dict):
            continue
        for metadata in section.get("metadata", []):
            if not isinstance(metadata, dict):
                continue
            title = str(metadata.get("title", "")).strip().lower()
            if title == "album":
                album_text = str(metadata.get("text", "")).strip()
                return album_text or None
    return None


def prepare_lyrics_for_track(
    result: Dict[str, Any],
    title: str,
    artist: str,
    record_start_monotonic: Optional[float] = None,
) -> None:
    """Fetches LRCLIB lyrics for a newly recognized track and seeds (or refines)
    the sync anchor.

    `record_start_monotonic` is the time.monotonic() at the moment audio
    capture began. The Shazam offset is the song-position at that moment, so
    using it as our anchor automatically subtracts recording + recognition +
    LRCLIB-fetch latency from the live playback estimate.
    """
    if not config.get("lyrics", {}).get("enabled", True):
        clear_lyrics_state()
        return

    track_info = result.get("track", {})
    album_name = extract_album_name(track_info)
    duration_seconds = extract_track_duration_seconds(track_info)
    shazam_offset_seconds = extract_match_offset_seconds(result)
    track_key = build_track_key(title, artist)

    # Anchor at the moment audio capture began. Fall back to "now" only if the
    # caller didn't thread the timestamp (e.g. legacy callsite).
    anchor_monotonic = record_start_monotonic if record_start_monotonic is not None else time.monotonic()

    lyrics_candidate = request_lrclib_candidate(title, artist, album_name, duration_seconds)
    if not lyrics_candidate:
        logger.info(f"No LRCLIB lyrics found for '{title}' by '{artist}'.")
        clear_lyrics_state()
        return

    synced_text = lyrics_candidate.get("syncedLyrics") or ""
    plain_text = lyrics_candidate.get("plainLyrics") or ""
    synced_lines = parse_synced_lyrics(synced_text) if synced_text else []
    lrc_offset_seconds = parse_lrc_offset_tag(synced_text) if synced_text else 0.0
    prefer_synced = bool(config.get("lyrics", {}).get("prefer_synced_lyrics", True))
    allow_plain = bool(config.get("lyrics", {}).get("show_plain_lyrics", False))

    if prefer_synced and not synced_lines:
        logger.info(f"Skipping unsynced lyrics for '{title}' by '{artist}'.")
        clear_lyrics_state()
        return

    if not synced_lines and not (allow_plain and plain_text.strip()):
        logger.info(f"LRCLIB returned no usable lyrics for '{title}' by '{artist}'.")
        clear_lyrics_state()
        return

    # Same track as currently loaded? Refine the anchor instead of resetting it
    # so the displayed lyric position doesn't jitter on every recognition cycle.
    same_track = (
        lyrics_state.get("track_key") == track_key
        and lyrics_state.get("anchor_monotonic") is not None
        and synced_lines
    )

    if same_track:
        logger.info(
            f"Refining lyrics anchor for '{title}' by '{artist}' "
            f"(shazam_offset={shazam_offset_seconds:.2f}s)."
        )
        lyrics_state["synced_lines"] = synced_lines
        lyrics_state["plain_lyrics"] = plain_text.strip()
        lyrics_state["lrc_offset_seconds"] = lrc_offset_seconds
        lyrics_state["source"] = "LRCLIB"
        refine_lyrics_anchor(shazam_offset_seconds, anchor_monotonic)
        return

    logger.info(
        f"Lyrics loaded for '{title}' by '{artist}' "
        f"(synced_lines={len(synced_lines)}, plain={bool(plain_text.strip())}, "
        f"shazam_offset={shazam_offset_seconds:.2f}s, lrc_offset={lrc_offset_seconds:.2f}s)."
    )
    set_lyrics_state(
        track_key,
        synced_lines,
        plain_text,
        shazam_offset_seconds,
        anchor_monotonic,
        lrc_offset_seconds,
        "LRCLIB",
    )


def build_synced_lyrics_lines(playback_seconds: float) -> List[str]:
    """Builds the visible synced lyric lines for the current playback time."""
    synced_lines = lyrics_state.get("synced_lines", [])
    if not synced_lines:
        return []

    current_index = -1
    for index, line in enumerate(synced_lines):
        if playback_seconds >= line["time_seconds"]:
            current_index = index
        else:
            break

    max_lines = max(1, int(config.get("lyrics", {}).get("max_visible_lines", 3)))
    if current_index < 0:
        visible_lines = synced_lines[:max_lines]
    else:
        visible_lines = synced_lines[current_index:current_index + max_lines]

    return [line["text"] for line in visible_lines if line["text"].strip()]


def compute_current_lyrics_lines() -> List[str]:
    """Calculates the currently visible lyric lines."""
    if lyrics_state.get("synced_lines"):
        anchor_monotonic = lyrics_state.get("anchor_monotonic")
        if anchor_monotonic is None:
            return []
        anchor_song_seconds = lyrics_state.get("anchor_song_seconds", 0.0)
        lrc_offset = lyrics_state.get("lrc_offset_seconds", 0.0)
        user_adjust = safe_float(config.get("lyrics", {}).get("offset_adjust_seconds")) or 0.0
        playback_seconds = (
            anchor_song_seconds
            + (time.monotonic() - anchor_monotonic)
            - lrc_offset
            + user_adjust
        )
        playback_seconds = max(0.0, playback_seconds)

        # Detect line advances → start a fade-in transition.
        active_index = -1
        for i, line in enumerate(lyrics_state["synced_lines"]):
            if playback_seconds >= line["time_seconds"]:
                active_index = i
            else:
                break
        if active_index != lyric_transition_state["last_index"] and is_motion_enabled(config):
            lyric_transition_state["active"] = True
            lyric_transition_state["start_monotonic"] = time.monotonic()
        lyric_transition_state["last_index"] = active_index

        return build_synced_lyrics_lines(playback_seconds)

    if config.get("lyrics", {}).get("show_plain_lyrics", True):
        plain_lines = [line.strip() for line in lyrics_state.get("plain_lyrics", "").splitlines() if line.strip()]
        max_lines = max(1, int(config.get("lyrics", {}).get("max_visible_lines", 3)))
        return plain_lines[:max_lines]

    return []


def update_lyrics_display_text():
    """Updates only the lyrics label text. Must run on the Tk thread."""
    render_lyrics_labels()


def render_lyrics_labels():
    """Renders synced lyric labels with an emphasis hierarchy: the active line is
    tinted with the cover-art accent color and rendered larger and brighter; the
    next and following lines are dimmed and smaller so the eye locks onto the
    current line first."""
    global lyrics_primary_label_id, lyrics_secondary_label_id, lyrics_tertiary_label_id
    if not canvas or not lyrics_layout_cache:
        return

    display_lines = lyrics_state.get("display_lines", [])
    visible_text = display_lines + ["", "", ""]
    x_pos = lyrics_layout_cache.get("x", 0)
    current_y = lyrics_layout_cache.get("primary_y", 0)
    width = int(lyrics_layout_cache.get("width", 0))
    anchor = lyrics_layout_cache.get("anchor", tk.N)
    justify = lyrics_layout_cache.get("justify", tk.CENTER)
    label_ids = [
        lyrics_primary_label_id,
        lyrics_secondary_label_id,
        lyrics_tertiary_label_id,
    ]
    primary_fill = lyrics_layout_cache.get("primary_fill", "#ffffff")
    # Blend accent toward white so it stays high-contrast against the vignette.
    accent_rgb = hex_to_rgb(accent_color_hex)
    active_rgb = mix_rgb(accent_rgb, (255, 255, 255), 0.35)
    active_fill = rgb_to_hex(active_rgb)
    label_configs = [
        {
            "base_size": int(lyrics_layout_cache.get("primary_font_size", 24)),
            "min_size": int(lyrics_layout_cache.get("primary_min_font_size", 18)),
            "max_height": int(lyrics_layout_cache.get("primary_max_height", 80)),
            "gap_after": int(lyrics_layout_cache.get("primary_gap_after", 18)),
            "fill": active_fill,
            "weight": "bold",
        },
        {
            "base_size": int(lyrics_layout_cache.get("secondary_font_size", 18)),
            "min_size": int(lyrics_layout_cache.get("secondary_min_font_size", 14)),
            "max_height": int(lyrics_layout_cache.get("secondary_max_height", 50)),
            "gap_after": int(lyrics_layout_cache.get("secondary_gap_after", 12)),
            "fill": "#a9b0bd",   # ~62% white on dark scrim
            "weight": "normal",
        },
        {
            "base_size": int(lyrics_layout_cache.get("tertiary_font_size", 16)),
            "min_size": int(lyrics_layout_cache.get("tertiary_min_font_size", 12)),
            "max_height": int(lyrics_layout_cache.get("tertiary_max_height", 44)),
            "gap_after": 0,
            "fill": "#6b7280",   # ~38% white
            "weight": "normal",
        },
    ]

    updated_ids: List[Optional[int]] = []
    previous_bottom = current_y
    previous_gap_after = 0

    for index, cfg in enumerate(label_configs):
        if index > 0:
            current_y = previous_bottom + previous_gap_after
        text = visible_text[index].strip()
        label_id = label_ids[index]

        if text:
            label_id, _, bbox = fit_canvas_title_font(
                canvas,
                label_id,
                text,
                x_pos,
                current_y,
                width,
                cfg["fill"],
                anchor,
                justify,
                cfg["base_size"],
                cfg["min_size"],
                cfg["max_height"],
                family=get_ui_font_family(),
                weight=cfg.get("weight", "bold"),
                slant="roman",
                tags=("main_text", "lyrics_text"),
            )
            previous_bottom = bbox[3]
        else:
            empty_font = (get_ui_font_family(), cfg["base_size"], cfg.get("weight", "bold"))
            if label_id:
                canvas.coords(label_id, x_pos, current_y)
                canvas.itemconfigure(
                    label_id,
                    text="",
                    font=empty_font,
                    fill=cfg["fill"],
                    width=width,
                    anchor=anchor,
                    justify=justify,
                )
            else:
                label_id = canvas.create_text(
                    x_pos,
                    current_y,
                    text="",
                    font=empty_font,
                    fill=cfg["fill"],
                    width=width,
                    anchor=anchor,
                    justify=justify,
                    tags=("main_text", "lyrics_text"),
                )
            previous_bottom = current_y

        previous_gap_after = cfg["gap_after"]
        updated_ids.append(label_id)

    lyrics_primary_label_id, lyrics_secondary_label_id, lyrics_tertiary_label_id = updated_ids
    canvas.tag_raise("main_text")


def classify_status_state(message: str) -> str:
    """Maps a status message string to a state token consumed by the pill renderer."""
    msg = (message or "").lower()
    if not msg.strip():
        return "idle"
    if "error" in msg or "offline" in msg:
        return "error"
    if "no match" in msg:
        return "no_match"
    if "init" in msg or "starting" in msg:
        return "starting"
    if "ready" in msg or "restored" in msg:
        return "ready"
    if "recogni" in msg or "retry" in msg:
        return "recognizing"
    if "listen" in msg or "fetch" in msg or "loading" in msg:
        return "listening"
    return "idle"


def render_status_pill(text_x: float, text_y: float, anchor: str, font_size: int) -> None:
    """Draws the status row as a rounded pill (dot + label).

    Dot color = accent (when actively working) or neutral grey (idle). The dot
    has a separate pulse animation driven by tick_status_pulse()."""
    global status_label_id, status_pill_bg_id, status_pill_dot_id, status_pill_layout
    if not canvas:
        return

    status_pill_layout = {
        "text_x": text_x, "text_y": text_y, "anchor": anchor, "font_size": font_size,
    }
    label_text = current_status_message or ""
    font_obj = (get_ui_font_family(), max(9, int(font_size * 0.95)), "bold")

    # Sizing — keep it tight: text + dot + horizontal padding.
    pad_x = max(10, int(font_size * 1.0))
    pad_y = max(5, int(font_size * 0.5))
    dot_radius = max(3, int(font_size * 0.32))
    dot_gap = max(6, int(font_size * 0.6))

    # Measure label.
    try:
        tk_font = tkFont.Font(family=get_ui_font_family(), size=max(9, int(font_size * 0.95)), weight="bold")
        text_width = tk_font.measure(label_text) if label_text else 0
        text_height = tk_font.metrics("linespace")
    except tk.TclError:
        text_width = max(40, len(label_text) * max(6, int(font_size * 0.55)))
        text_height = font_size + 4

    pill_w = pad_x * 2 + (dot_radius * 2) + dot_gap + text_width
    pill_h = max(text_height + pad_y * 2, dot_radius * 2 + pad_y * 2)
    if anchor == tk.W:
        x1 = text_x
        x2 = text_x + pill_w
    elif anchor == tk.E:
        x1 = text_x - pill_w
        x2 = text_x
    else:  # CENTER and others
        x1 = text_x - pill_w / 2
        x2 = text_x + pill_w / 2
    y1 = text_y
    y2 = text_y + pill_h

    # Pill background: dark, slight translucency-look via mixed dark grey.
    pill_fill = "#16181d"
    status_pill_bg_id = draw_rounded_rect(
        canvas, x1, y1, x2, y2,
        radius=pill_h / 2,
        fill=pill_fill,
        outline="",
        tags=("main_text", "status_pill"),
        existing_id=status_pill_bg_id,
    )

    # Dot color is driven by classified state.
    state = classify_status_state(label_text)
    if state in ("listening", "recognizing", "starting"):
        dot_color = accent_color_hex
    elif state == "error":
        dot_color = "#dc2626"
    elif state == "no_match":
        dot_color = "#8b919c"
    else:
        dot_color = "#5b6270"
    dot_cx = x1 + pad_x + dot_radius
    dot_cy = (y1 + y2) / 2
    if status_pill_dot_id:
        try:
            canvas.coords(status_pill_dot_id,
                          dot_cx - dot_radius, dot_cy - dot_radius,
                          dot_cx + dot_radius, dot_cy + dot_radius)
            canvas.itemconfigure(status_pill_dot_id, fill=dot_color, outline="")
        except tk.TclError:
            status_pill_dot_id = None
    if not status_pill_dot_id:
        status_pill_dot_id = canvas.create_oval(
            dot_cx - dot_radius, dot_cy - dot_radius,
            dot_cx + dot_radius, dot_cy + dot_radius,
            fill=dot_color, outline="", tags=("main_text", "status_pill"),
        )

    # Label text.
    text_anchor = tk.W
    text_pos_x = dot_cx + dot_radius + dot_gap
    text_pos_y = dot_cy
    if status_label_id:
        try:
            canvas.coords(status_label_id, text_pos_x, text_pos_y)
            canvas.itemconfigure(
                status_label_id,
                text=label_text,
                font=font_obj,
                fill="#e6e8ee",
                anchor=text_anchor,
            )
        except tk.TclError:
            status_label_id = None
    if not status_label_id:
        status_label_id = canvas.create_text(
            text_pos_x, text_pos_y,
            text=label_text,
            font=font_obj,
            fill="#e6e8ee",
            anchor=text_anchor,
            tags=("main_text", "status_pill"),
        )


def tick_status_pulse():
    """Drives the breathing-dot animation on the status pill.

    Cheap: only mutates one canvas oval's fill color on a sin curve; runs on a
    ~250ms cadence so it stays gentle on a Pi."""
    global status_pulse_job_id, status_pulse_phase
    status_pulse_job_id = None
    if not root or not canvas or not root.winfo_exists():
        return
    try:
        if status_pill_dot_id:
            state = classify_status_state(current_status_message)
            working = state in ("listening", "recognizing", "starting")
            if working:
                status_pulse_phase = (status_pulse_phase + 0.25) % (2 * math.pi)
                pulse = 0.5 + 0.5 * math.sin(status_pulse_phase)  # 0..1
                accent_rgb = hex_to_rgb(accent_color_hex)
                dim_rgb = mix_rgb(accent_rgb, (20, 22, 28), 0.55)
                rgb = mix_rgb(dim_rgb, accent_rgb, pulse)
                canvas.itemconfigure(status_pill_dot_id, fill=rgb_to_hex(rgb))
            else:
                canvas.itemconfigure(status_pill_dot_id, fill="#5b6270")
    except tk.TclError:
        pass

    try:
        status_pulse_job_id = root.after(220, tick_status_pulse)
    except tk.TclError:
        status_pulse_job_id = None


def tick_lyric_glow():
    """Drives the breathing-glow color cycle on the active lyric line.

    Sin-curve over ~3.6s, blending between the base active color and a
    brighter variant. Disabled when motion is reduced."""
    global lyric_glow_job_id, lyric_glow_phase
    lyric_glow_job_id = None
    if not root or not canvas or not root.winfo_exists():
        return
    if not is_motion_enabled(config):
        try:
            lyric_glow_job_id = root.after(1000, tick_lyric_glow)
        except tk.TclError:
            lyric_glow_job_id = None
        return
    try:
        if lyrics_primary_label_id and lyrics_state.get("synced_lines"):
            lyric_glow_phase = (lyric_glow_phase + (2 * math.pi / 36)) % (2 * math.pi)
            pulse = 0.5 + 0.5 * math.sin(lyric_glow_phase)
            accent_rgb = hex_to_rgb(accent_color_hex)
            base = mix_rgb(accent_rgb, (255, 255, 255), 0.35)
            bright = mix_rgb(accent_rgb, (255, 255, 255), 0.55)
            blended = mix_rgb(base, bright, pulse * 0.6)
            canvas.itemconfigure(lyrics_primary_label_id, fill=rgb_to_hex(blended))
    except tk.TclError:
        pass
    try:
        lyric_glow_job_id = root.after(100, tick_lyric_glow)
    except tk.TclError:
        lyric_glow_job_id = None


def begin_track_change_choreography(previous_accent: str) -> None:
    """Kicks off the 300ms color/meta crossfade after a different-track recognition."""
    if not is_motion_enabled(config):
        return
    track_change_state["active"] = True
    track_change_state["start_monotonic"] = time.monotonic()
    track_change_state["previous_accent"] = previous_accent or "#7c8fff"
    if root and root.winfo_exists():
        try:
            root.after(16, tick_track_change_choreography)
        except tk.TclError:
            pass


def tick_track_change_choreography():
    """Per-frame interpolation of accent color across UI elements during a track change."""
    global track_change_job_id
    track_change_job_id = None
    if not track_change_state.get("active") or not canvas:
        return
    elapsed = time.monotonic() - track_change_state["start_monotonic"]
    duration = track_change_state["duration"]
    if elapsed >= duration:
        track_change_state["active"] = False
        return
    t = ease_out_cubic(elapsed / duration)
    prev_rgb = hex_to_rgb(track_change_state["previous_accent"])
    new_rgb = hex_to_rgb(accent_color_hex)
    blended = rgb_to_hex(mix_rgb(prev_rgb, new_rgb, t))
    try:
        if progress_bar_fill_id:
            canvas.itemconfigure(progress_bar_fill_id, fill=blended)
        if status_pill_dot_id and classify_status_state(current_status_message) in ("listening", "recognizing", "starting"):
            canvas.itemconfigure(status_pill_dot_id, fill=blended)
    except tk.TclError:
        track_change_state["active"] = False
        return
    if root and root.winfo_exists():
        try:
            track_change_job_id = root.after(16, tick_track_change_choreography)
        except tk.TclError:
            track_change_job_id = None


def tick_lyric_transition():
    """Applies the per-frame fade-in for a freshly-advanced lyric line.

    Active for `lyric_transition_state['duration']` seconds after a line
    change; blends the active line's color from a low-opacity accent toward
    full while shifting it vertically by a few pixels (ease-out)."""
    if not lyric_transition_state.get("active"):
        return
    if not canvas or not lyrics_primary_label_id:
        return
    elapsed = time.monotonic() - lyric_transition_state["start_monotonic"]
    duration = lyric_transition_state["duration"]
    if elapsed >= duration:
        lyric_transition_state["active"] = False
        return
    t = ease_out_cubic(elapsed / duration)
    accent_rgb = hex_to_rgb(accent_color_hex)
    base = mix_rgb(accent_rgb, (255, 255, 255), 0.35)
    start_color = simulate_alpha_on_dark(rgb_to_hex(base), 0.4)
    end_color = rgb_to_hex(base)
    blended = mix_rgb(hex_to_rgb(start_color), hex_to_rgb(end_color), t)
    try:
        canvas.itemconfigure(lyrics_primary_label_id, fill=rgb_to_hex(blended))
        offset = int(8 * (1.0 - t))
        coords = canvas.coords(lyrics_primary_label_id)
        if len(coords) >= 2:
            base_y = lyrics_layout_cache.get("primary_y", coords[1])
            canvas.coords(lyrics_primary_label_id, coords[0], base_y + offset)
    except tk.TclError:
        lyric_transition_state["active"] = False


def render_progress_bar(window_width: int, window_height: int) -> None:
    """Draws a slim accent-tinted progress bar at the bottom of the canvas,
    reflecting the current song playback position from the sync anchor."""
    global progress_bar_track_id, progress_bar_fill_id
    if not canvas:
        return
    bar_height = 3
    margin = max(16, int(min(window_width, window_height) * 0.02))
    y = window_height - margin
    x1 = margin
    x2 = window_width - margin

    # Track (dim).
    if progress_bar_track_id:
        try:
            canvas.coords(progress_bar_track_id, x1, y, x2, y + bar_height)
            canvas.itemconfigure(progress_bar_track_id, fill="#2a2d35", outline="")
        except tk.TclError:
            progress_bar_track_id = None
    if not progress_bar_track_id:
        progress_bar_track_id = canvas.create_rectangle(
            x1, y, x2, y + bar_height,
            fill="#2a2d35", outline="",
            tags=("main_text", "progress_bar"),
        )

    # Fill (accent), width updated each tick by tick_progress_bar.
    if progress_bar_fill_id:
        try:
            canvas.coords(progress_bar_fill_id, x1, y, x1, y + bar_height)
            canvas.itemconfigure(progress_bar_fill_id, fill=accent_color_hex, outline="")
        except tk.TclError:
            progress_bar_fill_id = None
    if not progress_bar_fill_id:
        progress_bar_fill_id = canvas.create_rectangle(
            x1, y, x1, y + bar_height,
            fill=accent_color_hex, outline="",
            tags=("main_text", "progress_bar"),
        )

    tick_progress_bar()


def tick_progress_bar() -> None:
    """Updates the progress bar fill width based on the current lyrics anchor.
    Called from render_progress_bar (initial draw) and from refresh_lyrics_display."""
    if not canvas or not progress_bar_fill_id or not progress_bar_track_id:
        return
    try:
        track_coords = canvas.coords(progress_bar_track_id)
        if len(track_coords) < 4:
            return
        x1, y1, x2, y2 = track_coords
        synced_lines = lyrics_state.get("synced_lines") or []
        anchor_monotonic = lyrics_state.get("anchor_monotonic")
        anchor_song_seconds = lyrics_state.get("anchor_song_seconds", 0.0)
        if not synced_lines or anchor_monotonic is None:
            canvas.coords(progress_bar_fill_id, x1, y1, x1, y2)
            return
        # Use last synced timestamp as effective track length (good enough proxy).
        track_len = max(synced_lines[-1].get("time_seconds", 1.0), 30.0)
        playback = anchor_song_seconds + (time.monotonic() - anchor_monotonic)
        pct = max(0.0, min(1.0, playback / track_len))
        canvas.coords(progress_bar_fill_id, x1, y1, x1 + (x2 - x1) * pct, y2)
        canvas.itemconfigure(progress_bar_fill_id, fill=accent_color_hex)
    except tk.TclError:
        pass


def refresh_lyrics_display():
    """Refreshes the visible lyrics and re-schedules the next sync tick."""
    global lyrics_update_job_id
    lyrics_update_job_id = None

    if not root or not root.winfo_exists():
        return

    if not config.get("lyrics", {}).get("enabled", True):
        return

    next_lines = compute_current_lyrics_lines()
    if next_lines != lyrics_state.get("display_lines", []):
        lyrics_state["display_lines"] = next_lines
        update_lyrics_display_text()

    # Cheap per-tick: advance the progress bar fill width.
    tick_progress_bar()
    tick_lyric_transition()

    if lyrics_state.get("synced_lines"):
        interval_ms = max(100, int(config.get("lyrics", {}).get("refresh_interval_ms", 250)))
        try:
            lyrics_update_job_id = root.after(interval_ms, refresh_lyrics_display)
        except tk.TclError:
            lyrics_update_job_id = None


def restart_lyrics_sync():
    """Cancels any pending lyrics timer and refreshes the display immediately."""
    global lyrics_update_job_id
    if root and root.winfo_exists() and lyrics_update_job_id:
        try:
            root.after_cancel(lyrics_update_job_id)
        except ValueError:
            pass
        except tk.TclError:
            pass
    lyrics_update_job_id = None

    if not root or not root.winfo_exists():
        return

    refresh_lyrics_display()


# --- GUI Update Helpers ---
def schedule_gui_update(func, *args):
    """Schedules a function to run safely on the main Tkinter thread."""
    if root and root.winfo_exists():
        try:
            root.after(0, func, *args)
        except tk.TclError as e:
             logger.warning(f"TclError scheduling GUI update ({func.__name__}): {e}")
        except RuntimeError as e:
             logger.warning(f"RuntimeError scheduling GUI update ({func.__name__}): {e}")
    else:
        logger.debug(f"Skipped scheduling GUI update ({func.__name__}): root gone or doesn't exist.")

def set_status_message(message: str):
    """Safely update the global status message and trigger display update."""
    global current_status_message
    if message != current_status_message:
         current_status_message = message
         logger.debug(f"Status updated: {message}")
         schedule_gui_update(update_status_display_text)

def update_status_display_text():
    """Re-renders the status pill (background + dot + label) since the text
    length determines pill width."""
    if not canvas or not status_pill_layout:
        return
    try:
        render_status_pill(
            status_pill_layout["text_x"],
            status_pill_layout["text_y"],
            anchor=status_pill_layout["anchor"],
            font_size=status_pill_layout["font_size"],
        )
        canvas.tag_raise("status_pill")
    except tk.TclError:
        pass


def update_images() -> Dict[str, Any]:
    """Redraws main elements (BG, Cover Art, Text), returns layout info."""
    global bg_photo_ref, square_photo_ref, coverart_item_id
    global title_label_id, album_label_id, artist_label_id, status_label_id
    global lyrics_primary_label_id, lyrics_secondary_label_id, lyrics_tertiary_label_id
    global lyrics_layout_cache

    layout_info = {
        'window_width': 0,
        'window_height': 0,
        'square_size': 0,
        'square_x': 0,
        'square_y': 0,
        'title_y': 0,
        'album_y': 0,
        'artist_y': 0,
        'lyrics_x': 0,
        'lyrics_y': 0,
        'status_y': 0,
        'main_font_size': 10,
        'status_font_size': 8,
        'history_font_size': 7,
        'text_color': 'white',
        'is_fullscreen': False,
        'cinematic_mode': False,
    }

    if not root or not canvas or not root.winfo_exists():
        logger.warning("update_images: GUI not ready.")
        return layout_info

    try:
        window_width = root.winfo_width()
        window_height = root.winfo_height()
        is_fullscreen = root.attributes("-fullscreen")
        if window_width < 1 or window_height < 1:
            window_width = max(MIN_WINDOW_WIDTH, window_width)
            window_height = max(MIN_WINDOW_HEIGHT, window_height)
    except tk.TclError:
        logger.warning("update_images: Error getting window dimensions or attributes.")
        return layout_info

    layout_info.update({
        'window_width': window_width,
        'window_height': window_height,
        'is_fullscreen': is_fullscreen
    })

    # Idle splash takeover — skip rest of layout when active.
    global idle_splash_active
    has_active_track = bool(last_track_title)
    splash = should_show_idle_splash(
        last_match_monotonic=last_recognition_monotonic,
        now_monotonic=time.monotonic(),
        has_active_track=has_active_track,
        cfg=config,
    )
    idle_splash_active = splash
    if splash:
        render_idle_splash(window_width, window_height)
        layout_info["idle_splash"] = True
        return layout_info
    hide_idle_splash()

    image_file_path = IMAGE_PATH
    gui_cfg = config['gui']
    lyrics_cfg = config.get("lyrics", {})

    global accent_color_hex
    brightness = 0.2  # With vignette, foreground is always over a darkened scrim.
    try:
        if image_file_path.is_file():
            # Try Ken Burns crossfade first; fall back to static blurred bg.
            installed_kb = install_ken_burns(image_file_path, window_width, window_height)
            if installed_kb:
                # Accent extract from a fresh pre-vignette frame for true colors.
                try:
                    pre_vignette = create_blurred_background(
                        image_file_path, window_width, window_height, gui_cfg['blur_strength']
                    )
                    if pre_vignette is not None:
                        accent_color_hex = extract_accent_color(pre_vignette)
                except Exception as e:
                    logger.debug(f"Accent extract failed: {e}")
            else:
                blurred_pil_image = create_blurred_background(
                    image_file_path, window_width, window_height, gui_cfg['blur_strength']
                )
                if blurred_pil_image:
                    try:
                        accent_color_hex = extract_accent_color(blurred_pil_image)
                    except Exception as e:
                        logger.debug(f"Accent extract failed: {e}")
                    vignette_intensity = safe_float(gui_cfg.get("vignette_intensity")) or 0.55
                    blurred_pil_image = apply_vignette(blurred_pil_image, intensity=vignette_intensity)
                    bg_photo_ref = ImageTk.PhotoImage(blurred_pil_image)
                    canvas.delete("background")
                    canvas.create_image(0, 0, anchor=tk.NW, image=bg_photo_ref, tags=("background",))
                    canvas.tag_lower("background")
                else:
                    canvas.delete("background")
                    bg_photo_ref = None
        else:
            canvas.delete("background")
            bg_photo_ref = None
            canvas.config(bg="#0a0a0c")
    except Exception as e:
        logger.exception(f"Error processing or setting background image: {e}")
        canvas.delete("background")
        bg_photo_ref = None
        canvas.config(bg="#0a0a0c")

    # With the vignette overlay, foreground sits over a dark scrim regardless of
    # cover-art brightness — so we lock to a dark-mode foreground palette.
    text_color = "#ffffff"
    secondary_text_color = "#cdd2da"
    tertiary_text_color = "#8b919c"
    layout_info['text_color'] = text_color
    layout_info['accent_color'] = accent_color_hex

    margin_ratio = safe_float(lyrics_cfg.get("panel_margin_ratio")) or 0.05
    panel_gap_ratio = safe_float(lyrics_cfg.get("panel_gap_ratio")) or 0.04
    outer_margin = max(20, int(min(window_width, window_height) * margin_ratio))
    panel_gap = max(16, int(window_width * panel_gap_ratio))
    force_cinematic_mode = bool(lyrics_cfg.get("force_cinematic_mode", False))
    fullscreen_implies_cinematic = bool(lyrics_cfg.get("fullscreen_implies_cinematic_mode", True))
    cinematic_mode = bool(lyrics_cfg.get("enabled", True)) and (
        force_cinematic_mode
        or (fullscreen_implies_cinematic and bool(is_fullscreen))
        or window_width >= int(window_height * 1.18)
    )
    layout_info['cinematic_mode'] = cinematic_mode

    if cinematic_mode:
        left_block_width = max(360, int(window_width * 0.38))
        cover_gap = max(10, int(window_width * 0.012))
        square_size = max(190, min(int(window_width * 0.22), int(window_height * 0.30)))
        square_x = outer_margin + (square_size / 2)
        square_y = window_height - outer_margin - max(52, int(window_height * 0.07)) - (square_size / 2)
        metadata_x = outer_margin + square_size + cover_gap
        metadata_width = max(220, left_block_width - square_size - cover_gap)

        right_panel_left = outer_margin + left_block_width + panel_gap
        right_panel_right = window_width - outer_margin
        lyrics_panel_width = max(280, right_panel_right - right_panel_left)
        lyrics_x = right_panel_left + (lyrics_panel_width / 2)
        lyrics_y = max(outer_margin + 20, int(window_height * 0.43))
    else:
        border_ratio = gui_cfg['border_size_ratio']
        border_px = int(min(window_width, window_height) * border_ratio)
        square_size = max(MIN_WINDOW_WIDTH * 0.2, min(window_width, window_height) - 2 * border_px)
        square_x = window_width // 2
        if window_height > window_width:
            target_square_y = int(window_height * 0.35)
        else:
            target_square_y = int(window_height * 0.46)
        min_top_padding = gui_cfg.get('history_y_offset', 20)
        min_allowed_square_y = min_top_padding + (square_size / 2)
        square_y = max(target_square_y, int(min_allowed_square_y))
        metadata_x = window_width // 2
        metadata_width = max(220, int(window_width * 0.75))
        lyrics_panel_width = max(220, int(window_width * (safe_float(lyrics_cfg.get("width_ratio")) or 0.8)))
        lyrics_x = window_width // 2
        lyrics_y = square_y + (square_size / 2) + max(20, int(window_height * 0.04))

    layout_info.update({
        'square_size': square_size,
        'square_x': square_x,
        'square_y': square_y,
        'lyrics_x': lyrics_x,
        'lyrics_y': lyrics_y,
        'outer_margin': outer_margin,
    })

    if image_file_path.is_file():
        try:
            with Image.open(image_file_path) as img_reopened:
                square_pil_image = img_reopened.convert("RGB").resize(
                    (int(square_size), int(square_size)),
                    Image.Resampling.LANCZOS
                )
                square_photo_ref = ImageTk.PhotoImage(square_pil_image)
                if coverart_item_id:
                    canvas.itemconfig(coverart_item_id, image=square_photo_ref)
                    canvas.coords(coverart_item_id, square_x, square_y)
                else:
                    coverart_item_id = canvas.create_image(
                        square_x,
                        square_y,
                        anchor=tk.CENTER,
                        image=square_photo_ref,
                        tags=("coverart",)
                    )
                canvas.tag_raise(coverart_item_id)
                # Paint accent halo plate behind the cover art.
                render_cover_halo(square_x, square_y, int(square_size))
        except Exception as e:
            logger.exception(f"Error loading/processing main cover art image {image_file_path}: {e}")
            if coverart_item_id:
                canvas.delete(coverart_item_id)
                coverart_item_id = None
            square_photo_ref = None
    else:
        if coverart_item_id:
            canvas.delete(coverart_item_id)
            coverart_item_id = None
        square_photo_ref = None

    if cinematic_mode:
        type_scale = compute_type_scale(min(window_width, window_height))
        main_font_size = type_scale["title"]
        artist_font_size = type_scale["artist"]
        status_font_size = type_scale["status_pill"]
        lyrics_primary_font_size = type_scale["lyric_active"]
        # Context lines target ~55% of active per spec (active = ~1.6× context).
        lyrics_secondary_font_size = max(13, int(lyrics_primary_font_size * 0.55))
        lyrics_tertiary_font_size = max(12, int(lyrics_primary_font_size * 0.48))
    else:
        base_font_size = gui_cfg['base_font_size']
        scale_factor = 0.045
        upper_clamp = 32
        min_clamp = 8
        main_font_size = max(min_clamp, min(upper_clamp, int(square_size * scale_factor * (base_font_size / 10)))) if square_size > 0 else min_clamp + 2
        if not is_fullscreen and main_font_size > min_clamp + 1:
            main_font_size = max(min_clamp, main_font_size - 1)
        artist_font_size = main_font_size
        status_font_size = max(5, min(30, int(main_font_size * gui_cfg['status_font_size_ratio'] * 0.5)))
        lyrics_base = max(8, min(28, int(main_font_size * (safe_float(lyrics_cfg.get("font_scale")) or 0.75))))
        lyrics_primary_font_size = lyrics_base
        lyrics_secondary_font_size = max(8, int(lyrics_base * 0.86))
        lyrics_tertiary_font_size = max(8, int(lyrics_base * 0.78))

    history_font_size = max(6, min(20, int(main_font_size * gui_cfg['history_font_size_ratio'])))
    layout_info.update({
        'main_font_size': main_font_size,
        'status_font_size': status_font_size,
        'history_font_size': history_font_size,
    })

    try:
        title_font_obj = tkFont.Font(family=get_ui_font_family(), size=main_font_size, weight="bold")
        album_font_obj = tkFont.Font(family=get_ui_font_family(), size=max(12, int(artist_font_size * 0.95)), slant="italic")
        artist_font_obj = tkFont.Font(family=get_ui_font_family(), size=artist_font_size)
        status_font_obj = tkFont.Font(family=get_ui_font_family(), size=status_font_size)
        lyrics_primary_font_obj = tkFont.Font(family=get_ui_font_family(), size=lyrics_primary_font_size, weight="bold")
        lyrics_secondary_font_obj = tkFont.Font(family=get_ui_font_family(), size=lyrics_secondary_font_size, weight="bold")
        lyrics_tertiary_font_obj = tkFont.Font(family=get_ui_font_family(), size=lyrics_tertiary_font_size, weight="bold")
        title_line_height = title_font_obj.metrics("linespace")
        album_line_height = album_font_obj.metrics("linespace")
        artist_line_height = artist_font_obj.metrics("linespace")
        status_line_height = status_font_obj.metrics("linespace")
        primary_line_height = lyrics_primary_font_obj.metrics("linespace")
        secondary_line_height = lyrics_secondary_font_obj.metrics("linespace")
        tertiary_line_height = lyrics_tertiary_font_obj.metrics("linespace")
    except tk.TclError:
        title_font_obj = (get_ui_font_family(), main_font_size, "bold")
        album_font_obj = (get_ui_font_family(), max(12, int(artist_font_size * 0.95)), "italic")
        artist_font_obj = (get_ui_font_family(), artist_font_size)
        status_font_obj = (get_ui_font_family(), status_font_size)
        lyrics_primary_font_obj = (get_ui_font_family(), lyrics_primary_font_size, "bold")
        lyrics_secondary_font_obj = (get_ui_font_family(), lyrics_secondary_font_size, "bold")
        lyrics_tertiary_font_obj = (get_ui_font_family(), lyrics_tertiary_font_size, "bold")
        title_line_height = main_font_size * 1.2
        album_line_height = artist_font_size * 1.15
        artist_line_height = artist_font_size * 1.2
        status_line_height = status_font_size * 1.2
        primary_line_height = lyrics_primary_font_size * 1.2
        secondary_line_height = lyrics_secondary_font_size * 1.2
        tertiary_line_height = lyrics_tertiary_font_size * 1.2

    if cinematic_mode:
        cover_top = square_y - (square_size / 2)
        metadata_left = metadata_x
        title_y = cover_top + (square_size * 0.22)
        metadata_anchor = tk.W
        metadata_justify = tk.LEFT
        lyrics_primary_y = lyrics_y
        lyrics_primary_gap_after = max(18, int(window_height * 0.03))
        lyrics_secondary_gap_after = max(12, int(window_height * 0.02))
        lyrics_anchor = tk.N
        lyrics_justify = tk.CENTER
        main_text_x = metadata_left
        title_max_height = max(int(square_size * 0.44), int(title_line_height * 2.4))
        title_min_font_size = max(16, int(main_font_size * 0.58))
    else:
        base_y = square_y + square_size / 2
        title_y = base_y + title_line_height * 0.8
        lyrics_primary_y = lyrics_y
        lyrics_primary_gap_after = 12
        lyrics_secondary_gap_after = 10
        metadata_anchor = tk.CENTER
        metadata_justify = tk.CENTER
        lyrics_anchor = tk.N
        lyrics_justify = tk.CENTER
        main_text_x = metadata_x
        title_max_height = max(int(square_size * 0.18), int(title_line_height * 2.2))
        title_min_font_size = max(10, int(main_font_size * 0.72))

    lyrics_layout_cache = {
        "x": lyrics_x,
        "primary_y": lyrics_primary_y,
        "width": lyrics_panel_width,
        "anchor": lyrics_anchor,
        "justify": lyrics_justify,
        "primary_font_size": lyrics_primary_font_size,
        "secondary_font_size": lyrics_secondary_font_size,
        "tertiary_font_size": lyrics_tertiary_font_size,
        "primary_min_font_size": max(14 if cinematic_mode else 8, int(lyrics_primary_font_size * 0.62)),
        "secondary_min_font_size": max(12 if cinematic_mode else 8, int(lyrics_secondary_font_size * 0.68)),
        "tertiary_min_font_size": max(10 if cinematic_mode else 8, int(lyrics_tertiary_font_size * 0.72)),
        "primary_max_height": max(int(primary_line_height * 2.45), int(window_height * (0.14 if cinematic_mode else 0.09))),
        "secondary_max_height": max(int(secondary_line_height * 2.35), int(window_height * (0.10 if cinematic_mode else 0.07))),
        "tertiary_max_height": max(int(tertiary_line_height * 2.25), int(window_height * (0.08 if cinematic_mode else 0.06))),
        "primary_gap_after": lyrics_primary_gap_after,
        "secondary_gap_after": lyrics_secondary_gap_after,
        "primary_fill": text_color,
        "secondary_fill": secondary_text_color,
        "tertiary_fill": tertiary_text_color,
    }

    metadata_options = {
        'fill': text_color,
        'anchor': metadata_anchor,
        'justify': metadata_justify,
    }

    try:
        title_display_text = last_track_title
        album_text = last_album_name.strip()
        album_display_text = album_text
        artist_display_text = format_artist_label(last_artist_name)

        title_label_id, title_font_obj, title_bbox = fit_canvas_title_font(
            canvas,
            title_label_id,
            title_display_text,
            main_text_x,
            title_y,
            metadata_width,
            text_color,
            metadata_anchor,
            metadata_justify,
            main_font_size,
            title_min_font_size,
            title_max_height,
        )
        title_block_bottom = title_bbox[3]
        title_to_album_gap = 8 if cinematic_mode else max(4, int(album_line_height * 0.35))
        album_to_artist_gap = 8 if cinematic_mode else max(4, int(artist_line_height * 0.2))
        artist_to_status_gap = 12 if cinematic_mode else max(6, int(status_line_height * 0.45))

        album_y = title_block_bottom + title_to_album_gap
        if album_text:
            artist_y = album_y + album_line_height + album_to_artist_gap
        else:
            artist_y = title_block_bottom + title_to_album_gap
        status_y = artist_y + artist_line_height + artist_to_status_gap

        layout_info.update({
            'title_y': title_y,
            'album_y': album_y,
            'artist_y': artist_y,
            'status_y': status_y,
        })

        if album_label_id:
            canvas.coords(album_label_id, main_text_x, album_y)
            canvas.itemconfigure(album_label_id, text=album_display_text, font=album_font_obj, fill=secondary_text_color, anchor=metadata_anchor, justify=metadata_justify, width=metadata_width)
        else:
            album_label_id = canvas.create_text(main_text_x, album_y, text=album_display_text, font=album_font_obj, tags=("main_text",), fill=secondary_text_color, anchor=metadata_anchor, justify=metadata_justify, width=metadata_width)

        if artist_label_id:
            canvas.coords(artist_label_id, main_text_x, artist_y)
            canvas.itemconfigure(artist_label_id, text=artist_display_text, font=artist_font_obj, fill=secondary_text_color, anchor=metadata_anchor, justify=metadata_justify, width=metadata_width)
        else:
            artist_label_id = canvas.create_text(main_text_x, artist_y, text=artist_display_text, font=artist_font_obj, tags=("main_text",), fill=secondary_text_color, anchor=metadata_anchor, justify=metadata_justify, width=metadata_width)

        # Status now renders as a pill (rounded surface + animated dot + label)
        # anchored at the same status_y position, instead of plain canvas text.
        render_status_pill(
            main_text_x,
            status_y,
            anchor=metadata_anchor,
            font_size=status_font_size,
        )

        canvas.delete("metadata_icon")

        render_lyrics_labels()
        render_progress_bar(window_width, window_height)
        canvas.tag_raise("main_text")
        canvas.tag_raise("status_pill")
        canvas.tag_raise("progress_bar")
    except tk.TclError as e:
        logger.warning(f"TclError updating text labels: {e}. IDs reset.")
        global status_pill_bg_id, status_pill_dot_id, progress_bar_track_id, progress_bar_fill_id
        title_label_id = None
        album_label_id = None
        artist_label_id = None
        status_label_id = None
        status_pill_bg_id = None
        status_pill_dot_id = None
        progress_bar_track_id = None
        progress_bar_fill_id = None
        lyrics_primary_label_id = None
        lyrics_secondary_label_id = None
        lyrics_tertiary_label_id = None

    logger.debug("Main images and text updated.")
    return layout_info


def redraw_history_display(layout_info: Dict[str, Any]):
    """Redraws the song history panel based on available space and layout mode."""
    global history_photo_refs
    if not canvas or not root or not root.winfo_exists():
        logger.debug("redraw_history_display: Canvas or root not ready.")
        return

    logger.info("--- Redrawing History Display ---")
    canvas.delete("history_item")
    history_photo_refs.clear()

    if layout_info.get("cinematic_mode"):
        if len(song_history_list) < 2:
            logger.info("--- History Redraw End (No cinematic history items) ---")
            return

        lyrics_cfg = config.get("lyrics", {})
        text_color = layout_info.get('text_color', 'white')
        history_max_items = max(1, int(lyrics_cfg.get("cinematic_history_max_items", 4)))
        history_scale = safe_float(lyrics_cfg.get("cinematic_history_scale")) or 0.44
        history_gap = max(6, int(lyrics_cfg.get("cinematic_history_gap", 12)))
        history_title_scale = safe_float(lyrics_cfg.get("cinematic_history_title_scale")) or 0.15
        history_artist_scale = safe_float(lyrics_cfg.get("cinematic_history_artist_scale")) or 0.12
        history_text_gap = max(10, int(history_gap * 0.8))
        square_size = max(1, int(layout_info.get("square_size", 1)))
        square_x = float(layout_info.get("square_x", 0))
        square_y = float(layout_info.get("square_y", 0))
        top_margin = max(history_gap, int(layout_info.get("outer_margin", history_gap)))
        square_left = int(square_x - (square_size / 2))
        square_top = int(square_y - (square_size / 2))
        history_size = max(54, int(square_size * history_scale))
        history_text_width = max(120, int(square_size * 1.35))
        items_to_draw = song_history_list[1: 1 + history_max_items]

        history_title_font_size = max(9, int(history_size * history_title_scale))
        history_artist_font_size = max(8, int(history_size * history_artist_scale))
        try:
            history_title_font = tkFont.Font(family=get_ui_font_family(), size=history_title_font_size, slant="italic")
            history_artist_font = tkFont.Font(family=get_ui_font_family(), size=history_artist_font_size, weight="bold")
            history_artist_line_height = history_artist_font.metrics("linespace")
        except tk.TclError:
            history_title_font = (get_ui_font_family(), history_title_font_size, "italic")
            history_artist_font = (get_ui_font_family(), history_artist_font_size, "bold")
            history_artist_line_height = history_artist_font_size * 1.2

        if not items_to_draw:
            logger.info("--- History Redraw End (No cinematic history entries after current track) ---")
            return

        item_count = max(1, len(items_to_draw))
        for index, item in enumerate(items_to_draw):
            img_path_str = item.get('image_path')
            if not img_path_str:
                continue
            img_path = Path(img_path_str)
            if not img_path.is_file():
                continue

            img_x = square_left
            img_y = square_top - ((index + 1) * (history_size + history_gap))
            if img_y < top_margin:
                break
            text_x = img_x + history_size + history_text_gap
            title_y = img_y + max(0, int(history_size * 0.08))

            # Newest = 100%, oldest = 50%, linear.
            opacity = 1.0 - (index / max(1, item_count - 1)) * 0.5 if item_count > 1 else 1.0
            faded_title = simulate_alpha_on_dark(text_color, opacity)
            faded_artist = simulate_alpha_on_dark("#cdd2da", opacity * 0.85)

            try:
                with Image.open(img_path) as img:
                    img = img.convert("RGB").resize((history_size, history_size), Image.Resampling.LANCZOS)
                    photo_ref = ImageTk.PhotoImage(img)
                    canvas_img_id = canvas.create_image(
                        img_x,
                        img_y,
                        anchor=tk.NW,
                        image=photo_ref,
                        tags=("history_item", "history_image")
                    )
                    history_title_max_height = max(int(history_size * 0.52), int(history_title_font_size * 2.0))
                    history_title_min_size = max(8, int(history_title_font_size * 0.72))
                    canvas_title_id, _, title_bbox = fit_canvas_title_font(
                        canvas,
                        None,
                        item.get('title', 'Unknown Title'),
                        text_x,
                        title_y,
                        history_text_width,
                        faded_title,
                        tk.NW,
                        tk.LEFT,
                        history_title_font_size,
                        history_title_min_size,
                        history_title_max_height,
                        family=get_ui_font_family(),
                        weight="normal",
                        slant="italic",
                        tags=("history_item", "history_text", "history_title"),
                    )
                    artist_y = title_bbox[3] + max(3, int(history_size * 0.04))
                    canvas_artist_id = canvas.create_text(
                        text_x,
                        artist_y,
                        text=item.get('artist', 'Unknown Artist'),
                        anchor=tk.NW,
                        justify=tk.LEFT,
                        width=history_text_width,
                        font=history_artist_font,
                        fill=faded_artist,
                        tags=("history_item", "history_text", "history_artist")
                    )
                    history_photo_refs.append({
                        'image_ref': photo_ref,
                        'canvas_img_id': canvas_img_id,
                        'canvas_title_id': canvas_title_id,
                        'canvas_artist_id': canvas_artist_id
                    })
                    canvas.tag_raise(canvas_img_id)
                    canvas.tag_raise(canvas_title_id)
                    canvas.tag_raise(canvas_artist_id)
            except Exception as e:
                logger.exception(f"ERROR loading cinematic history image {img_path}: {e}")

        canvas.tag_lower("background")
        canvas.tag_raise("history_item")
        if coverart_item_id:
            canvas.tag_raise(coverart_item_id)
        canvas.tag_raise("main_text")
        logger.info(f"--- History Redraw End (Cinematic thumbnails: {len(history_photo_refs)}) ---")
        return

    if len(song_history_list) < 2:
        logger.info("Not enough history items (need >= 2) to display previous songs.")
        logger.info("--- History Redraw End (Not Enough Items) ---")
        return

    logger.info(f"Total songs in memory: {len(song_history_list)}. Attempting to display previous songs.")

    gui_cfg = config['gui']
    max_items = gui_cfg['history_max_items']
    art_size_config = gui_cfg['history_art_size']
    padding = gui_cfg['history_item_padding']
    x_offset = gui_cfg['history_x_offset']
    y_offset = gui_cfg['history_y_offset']
    min_side_width_config = gui_cfg['history_min_side_width']
    side_buffer = gui_cfg['layout_side_min_buffer']
    below_buffer = gui_cfg['layout_below_min_buffer']
    win_w = layout_info['window_width']
    win_h = layout_info['window_height']
    sq_x = layout_info['square_x']
    sq_y = layout_info['square_y']
    sq_size = layout_info['square_size']
    history_font_size = layout_info['history_font_size']
    text_color = layout_info['text_color']
    is_fullscreen = layout_info.get('is_fullscreen', False)

    history_font_size_actual = max(5, history_font_size - 1)
    logger.debug(f"Base history font size: {history_font_size}, Actual used: {history_font_size_actual}")

    try:
        history_font_italic = tkFont.Font(family=get_ui_font_family(), size=history_font_size_actual, slant="italic")
        history_font_bold = tkFont.Font(family=get_ui_font_family(), size=history_font_size_actual, weight="bold")
        history_line_height = history_font_bold.metrics("linespace")
        text_block_height_for_spacing = (history_line_height * 2.8) + 4
    except tk.TclError:
        logger.warning("tkFont failed for history fonts.")
        history_font_italic = (get_ui_font_family(), history_font_size_actual, "italic")
        history_font_bold = (get_ui_font_family(), history_font_size_actual, "bold")
        history_line_height = history_font_size_actual * 1.3
        text_block_height_for_spacing = (history_line_height * 2.8) + 4

    current_art_size = art_size_config
    temp_available_width_left = max(0, (sq_x - sq_size // 2) - x_offset - side_buffer)
    temp_available_height_side = max(0, win_h - 2 * y_offset)
    temp_history_entry_height = max(art_size_config, text_block_height_for_spacing) + padding
    is_potentially_left_mode = (temp_available_width_left >= min_side_width_config and
                               temp_available_height_side >= temp_history_entry_height)

    if is_potentially_left_mode and is_fullscreen:
        current_art_size = int(text_block_height_for_spacing)
        logger.info(f"Fullscreen Left mode: Adjusting history art size to text height: {current_art_size}")
    else:
        logger.info(f"Not Fullscreen Left mode or Below Mode: Using config history art size: {current_art_size}")

    history_entry_height = max(current_art_size, text_block_height_for_spacing) + padding
    logger.debug(f"Final History Entry Height for layout/spacing: {history_entry_height:.0f} (using art_size={current_art_size})")

    layout_mode: Literal["Hidden", "Left", "Below"] = "Hidden"
    available_width_left = max(0, (sq_x - sq_size // 2) - x_offset - side_buffer)
    available_height_side = max(0, win_h - 2 * y_offset)
    status_text_y = layout_info.get('status_y', win_h)
    available_height_below = max(0, win_h - status_text_y - (below_buffer * 2.0))

    logger.info(f"[Layout Check] Window: {win_w}x{win_h}, Square @({sq_x},{sq_y}) Size:{sq_size:.0f}, StatusY:{status_text_y:.0f}")
    logger.info(f"[Layout Check] Config: MinSideW={min_side_width_config}, EntryH={history_entry_height:.0f}, ArtSize={current_art_size}, TxtBlkH_Layout={text_block_height_for_spacing:.0f}")
    logger.info(f"[Layout Check] Available: W_Left={available_width_left:.0f}, H_Side={available_height_side:.0f}, H_Below={available_height_below:.0f}")

    can_fit_vertically_side = available_height_side >= history_entry_height
    can_fit_vertically_below = available_height_below >= history_entry_height

    if available_width_left >= min_side_width_config and can_fit_vertically_side:
        layout_mode = "Left"
        logger.info(f"[Layout Decision] Mode set to 'Left' (W_Left >= MinSideW AND H_Side >= EntryH)")
    elif can_fit_vertically_below:
        layout_mode = "Below"
        logger.info(f"[Layout Decision] Mode set to 'Below' (H_Below >= EntryH)")
    else:
        layout_mode = "Hidden"
        logger.info(f"[Layout Decision] Mode set to 'Hidden' (Insufficient space)")

    if layout_mode == "Hidden":
        logger.info("--- History Redraw End (Hidden) ---")
        return

    items_to_draw = song_history_list[1 : max_items + 1]
    num_items_actually_drawing = 0
    initial_y_pos = y_offset
    estimated_max_text_width = max(150, min(win_w * 0.6, 500))

    if layout_mode == "Left":
        max_items_fit_height = int(available_height_side // history_entry_height) if history_entry_height > 0 else 0
        num_items_to_draw_actual = min(len(items_to_draw), max_items_fit_height)
        if num_items_to_draw_actual > 0:
            total_list_height = (history_entry_height * num_items_to_draw_actual) - padding
            available_draw_height = win_h - 2 * y_offset
            initial_y_pos = max(y_offset, (available_draw_height - total_list_height) // 2 + y_offset)
            logger.debug(f"Left Mode Centering: MaxFit={max_items_fit_height}, DrawActual={num_items_to_draw_actual}, ListH={total_list_height:.0f}, AvailH={available_draw_height:.0f}, StartY={initial_y_pos:.0f}")
        else:
            logger.warning("Left Mode: Calculated 0 items fit vertically.")
            layout_mode = "Hidden"

    elif layout_mode == "Below":
        max_items_fit_height = int(available_height_below // history_entry_height) if history_entry_height > 0 else 0
        num_items_to_draw_actual = min(len(items_to_draw), max_items_fit_height)
        initial_y_pos = status_text_y + (below_buffer * 2.0)
        if num_items_to_draw_actual <= 0:
             logger.warning("Below Mode: Calculated 0 items fit vertically.")
             layout_mode = "Hidden"

    if layout_mode == "Hidden":
        logger.info("--- History Redraw End (Hidden after fit check) ---")
        return

    y_pos = initial_y_pos
    items_to_draw_fitting = items_to_draw[:num_items_to_draw_actual]
    logger.info(f"Attempting to draw {len(items_to_draw_fitting)} items in '{layout_mode}' mode...")

    for i, item in enumerate(items_to_draw_fitting):
        logger.debug(f"Processing history item index {i} (Overall index {i+1}): Title='{item.get('title')}'")
        img_path_str = item.get('image_path')
        canvas_img_id = None
        photo_ref = None
        canvas_title_id = None
        canvas_artist_id = None

        img_y = y_pos
        img_anchor = tk.NW
        text_anchor = tk.NW
        text_justify = tk.LEFT

        if layout_mode == "Left":
            img_x = x_offset
            text_x = x_offset + current_art_size + 10
            text_wrap_width = max(10, available_width_left - (current_art_size + 10))
        elif layout_mode == "Below":
             item_text_width = estimated_max_text_width
             item_block_width = current_art_size + 10 + item_text_width
             item_block_start_x = max(x_offset, (win_w - item_block_width) // 2)
             img_x = item_block_start_x
             text_x = img_x + current_art_size + 10
             text_wrap_width = max(10, item_text_width)

        title_y = y_pos
        title_text = item.get('title', 'Unknown Title')
        history_title_max_height = max(int(current_art_size * 0.7), int(history_font_size_actual * 2.2))
        history_title_min_size = max(5, int(history_font_size_actual * 0.72))

        next_y_increment = history_entry_height

        logger.debug(f"  Item index {i} ({layout_mode}): Final Coords Img=({img_x:.0f},{img_y:.0f}, Size:{current_art_size}) Title=({text_x:.0f},{title_y:.0f})")

        if img_path_str:
            img_path = Path(img_path_str)
            if img_path.is_file():
                try:
                    with Image.open(img_path) as img:
                        img = img.resize((current_art_size, current_art_size), Image.Resampling.LANCZOS)
                        photo_ref = ImageTk.PhotoImage(img)
                        canvas_img_id = canvas.create_image(img_x, img_y,
                                                            anchor=img_anchor, image=photo_ref,
                                                            tags=("history_item", "history_image"))
                        logger.debug(f"  Item index {i} image created ID: {canvas_img_id}")
                except Exception as e:
                    logger.exception(f"  ERROR loading/drawing history image {img_path} for item index {i}: {e}")
                    photo_ref = None
            else:
                logger.warning(f"  History image file missing for item index {i}: {img_path}")
        else:
            logger.warning(f"  History item index {i} missing image path.")

        try:
            canvas_title_id, _, title_bbox = fit_canvas_title_font(
                canvas,
                None,
                title_text,
                text_x,
                title_y,
                text_wrap_width,
                text_color,
                text_anchor,
                text_justify,
                history_font_size_actual,
                history_title_min_size,
                history_title_max_height,
                family=get_ui_font_family(),
                weight="normal",
                slant="italic",
                tags=("history_item", "history_text", "history_title"),
            )
            artist_y = title_bbox[3] + max(3, int(history_line_height * 0.25))
            logger.debug(f"  Item index {i} title text created ID: {canvas_title_id}")
        except Exception as e:
             logger.exception(f"  ERROR creating history title text for item index {i}: {e}")
             artist_y = title_y + history_line_height

        artist_text = item.get('artist', 'Unknown Artist')
        try:
            canvas_artist_id = canvas.create_text(text_x, artist_y, text=artist_text,
                                           anchor=text_anchor, justify=text_justify,
                                           font=history_font_bold, fill=text_color,
                                           width=text_wrap_width,
                                           tags=("history_item", "history_text", "history_artist"))
            logger.debug(f"  Item index {i} artist text created ID: {canvas_artist_id}")
        except Exception as e:
             logger.exception(f"  ERROR creating history artist text for item index {i}: {e}")

        history_photo_refs.append({
            'image_ref': photo_ref,
            'canvas_img_id': canvas_img_id,
            'canvas_title_id': canvas_title_id,
            'canvas_artist_id': canvas_artist_id
            })

        if canvas_img_id: canvas.tag_raise(canvas_img_id)
        if canvas_title_id: canvas.tag_raise(canvas_title_id)
        if canvas_artist_id: canvas.tag_raise(canvas_artist_id)

        y_pos += next_y_increment

    canvas.tag_lower("background")
    canvas.tag_raise("history_item")
    if coverart_item_id:
        canvas.tag_raise(coverart_item_id)
    canvas.tag_raise("main_text")

    logger.info(f"History display attempted draw of {len(history_photo_refs)} items in '{layout_mode}' mode. Layering adjusted.")
    logger.info("--- History Redraw End ---")


# --- GUI Update & Event Handling ---
def update_gui(update_data: Dict[str, Any]):
    """Updates GUI based on processed data from background thread. Runs on main thread."""
    global last_track_title, last_album_name, last_artist_name, last_persistent_image_path
    status = update_data.get('status')
    title = update_data.get('title')
    album = update_data.get('album', '')
    artist = update_data.get('artist')
    persistent_path = update_data.get('persistent_path')
    image_updated = update_data.get('image_updated', False)
    error_message = update_data.get('message')

    redraw_needed = False
    status_to_set = current_status_message

    logger.debug(f"GUI Update Received: Status='{status}', Title='{title}', Artist='{artist}', ImgUpd={image_updated}, ErrMsg='{error_message}'")

    if status == 'success':
        is_new_song_text = (title != last_track_title or artist != last_artist_name)

        if is_new_song_text:
            logger.info(f"GUI update: New song '{title}' by {artist}.")
            last_track_title = title
            last_album_name = album
            last_artist_name = artist
            last_persistent_image_path = persistent_path
            status_to_set = "Ready"
            redraw_needed = True
            restart_lyrics_sync()
            if not image_updated and error_message and error_message != "Used Cache":
                 logger.warning(f"New song text displayed, but image update failed: {error_message}. Showing previous/placeholder image.")
                 status_to_set = f"Ready (Image Error: {error_message})"
            elif error_message == "Used Cache":
                status_to_set = "Ready (Used Cache)"

        else:
            logger.info("GUI update: Same song recognized.")
            status_to_set = "Ready (Same Song)"
            if image_updated and error_message != "Used Cache":
                logger.info("Image refreshed for the same song.")
                last_album_name = album
                last_persistent_image_path = persistent_path
                redraw_needed = True
                status_to_set = "Ready (Image Refreshed)"
            elif error_message == "Used Cache":
                status_to_set = "Ready (Used Cache)"

    elif status == 'no_match':
        logger.info("GUI update: No match found.")
        status_to_set = "No Match Found"

    elif status == 'error':
        logger.error(f"GUI update: Received error status. Message: '{error_message}'")
        status_to_set = error_message or "Error: Unknown"

    else:
         logger.warning(f"GUI update: Received unknown status '{status}'")
         status_to_set = "Error: Internal State"

    set_status_message(status_to_set)

    if redraw_needed:
        logger.debug("Scheduling full redraw due to state change.")
        schedule_gui_update(trigger_full_redraw)


def trigger_full_redraw():
     """Safely calls functions to redraw all main GUI elements. Must run on Tk thread."""
     if not root or not canvas or not root.winfo_exists():
          logger.debug("Skip redraw: GUI not ready.")
          return
     logger.debug("Triggering full redraw...")
     try:
         layout_info = update_images()
         redraw_history_display(layout_info)
         logger.debug("Full redraw complete.")
     except tk.TclError as e:
         logger.error(f"TclError during full redraw: {e}")
     except Exception as e:
         logger.exception(f"Unexpected error during full redraw: {e}")


def get_monitor_for_window() -> Optional[Any]:
    """Finds the screeninfo monitor object the window is currently on."""
    if not root or not root.winfo_exists(): return None
    try:
        root.update_idletasks()
        window_x = root.winfo_rootx()
        window_y = root.winfo_rooty()
        window_w = root.winfo_width()
        window_h = root.winfo_height()

        monitors = get_monitors()
        logger.debug(f"Win pos: ({window_x}, {window_y}), size: ({window_w}x{window_h}). Checking {len(monitors)} monitors.")

        best_match = None
        max_overlap = 0

        for i, monitor in enumerate(monitors):
            logger.debug(f"  Mon {i}: X={monitor.x},Y={monitor.y},W={monitor.width},H={monitor.height}")
            overlap_x1 = max(window_x, monitor.x)
            overlap_y1 = max(window_y, monitor.y)
            overlap_x2 = min(window_x + window_w, monitor.x + monitor.width)
            overlap_y2 = min(window_y + window_h, monitor.y + monitor.height)
            overlap_width = max(0, overlap_x2 - overlap_x1)
            overlap_height = max(0, overlap_y2 - overlap_y1)
            overlap_area = overlap_width * overlap_height

            if overlap_area > max_overlap:
                max_overlap = overlap_area
                best_match = monitor

        if best_match:
            return best_match
        elif monitors:
            logger.warning("Could not determine monitor based on overlap. Falling back to primary monitor.")
            return monitors[0]
        else:
            logger.error("screeninfo returned no monitors.")
            return None

    except tk.TclError as e:
        logger.warning(f"TclError getting window info for monitor check: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error getting monitor info: {e}")
        try:
            monitors = get_monitors()
            return monitors[0] if monitors else None
        except:
            return None


def toggle_fullscreen(event=None):
    """Toggles borderless fullscreen mode for the current monitor."""
    if not root or not root.winfo_exists(): return
    is_fullscreen = root.attributes("-fullscreen")
    logger.info(f"Toggling fullscreen: {'Disabling' if is_fullscreen else 'Enabling'}")

    if is_fullscreen:
        root.attributes("-fullscreen", False)
    else:
        monitor = get_monitor_for_window()
        if monitor:
            root.geometry(f"{monitor.width}x{monitor.height}+{monitor.x}+{monitor.y}")
            root.attributes("-fullscreen", True)
        else:
             logger.warning("No monitor found for fullscreen toggle. Using default fullscreen.")
             root.attributes("-fullscreen", True)

    schedule_gui_update(lambda: root.after(150, trigger_full_redraw))

def hide_cursor():
    """Hides the mouse cursor."""
    if root and root.winfo_exists():
        try:
            root.config(cursor="none")
        except tk.TclError:
            pass

def show_cursor():
    """Shows the mouse cursor."""
    if root and root.winfo_exists():
        try:
            root.config(cursor="")
        except tk.TclError:
            pass

def reset_cursor_hide_timer(event=None):
    """Resets the timer to hide the cursor after inactivity."""
    global cursor_hide_timer_id
    if not root or not root.winfo_exists(): return

    if cursor_hide_timer_id:
        try:
            root.after_cancel(cursor_hide_timer_id)
        except ValueError:
            pass
        cursor_hide_timer_id = None

    show_cursor()
    try:
        cursor_hide_timer_id = root.after(5000, hide_cursor)
    except tk.TclError:
        pass

def on_resize(event=None):
    """Handles window resize events with debouncing."""
    global resize_job_id
    if not root or not root.winfo_exists(): return

    if event and hasattr(event, 'widget') and event.widget != root:
         return

    if resize_job_id:
        try:
            root.after_cancel(resize_job_id)
        except ValueError:
            pass
        resize_job_id = None

    try:
        resize_job_id = root.after(300, trigger_full_redraw)
    except tk.TclError:
        pass

def on_closing():
    """Handles the window closing event for graceful shutdown."""
    global recognition_thread, recognition_thread_stop_event, root, lyrics_update_job_id
    logger.info("Shutdown requested via window close.")

    set_status_message("Shutting down...")

    if root and root.winfo_exists() and lyrics_update_job_id:
        try:
            root.after_cancel(lyrics_update_job_id)
        except (ValueError, tk.TclError):
            pass
        lyrics_update_job_id = None

    if recognition_thread_stop_event:
        recognition_thread_stop_event.set()

    if recognition_thread and recognition_thread.is_alive():
        logger.info(f"Waiting for {recognition_thread.name} to join (max 5s)...")
        recognition_thread.join(timeout=5.0)
        if recognition_thread.is_alive():
            logger.warning(f"{recognition_thread.name} did not stop gracefully within timeout.")
        else:
            logger.info(f"{recognition_thread.name} finished.")
    else:
        logger.debug("Recognition thread was not running or already finished.")

    try:
        retain_count = config['gui'].get('history_max_items_retain', 20)
        cleanup_old_history_images(keep_count=retain_count)
    except Exception as e:
        logger.exception("Error occurred during history cleanup call.")

    safe_remove(TEMP_IMAGE_PATH, "temp image on closing")

    if root:
        logger.info("Destroying Tkinter window.")
        try:
             root.after_idle(root.destroy)
        except tk.TclError as e:
             logger.warning(f"TclError during root.destroy(): {e}")
        root = None

    logger.info("Shutdown sequence complete.")


async def process_recognition_result(
    result: Dict[str, Any],
    record_start_monotonic: Optional[float] = None,
) -> Dict[str, Any]:
    """Processes successful Shazam result: cache/download image, add to history, save state."""
    global song_history_list, last_recognition_monotonic
    last_recognition_monotonic = time.monotonic()
    previous_track_key = build_track_key(last_track_title, last_artist_name) if last_track_title else None
    previous_accent = accent_color_hex
    track_info = result.get('track', {})
    new_title = track_info.get('title', 'Unknown Title')
    new_artist = track_info.get('subtitle', 'Unknown Artist')
    new_album = extract_album_name(track_info) or ""

    logger.info(f"Processing result: '{new_title}' by '{new_artist}'")

    persistent_path_for_this_song: Optional[str] = None
    image_processed_successfully = False
    last_image_error_message = ""
    current_display_image_path = IMAGE_PATH
    cache_hit = False

    logger.debug("Checking history cache for existing cover art...")
    for history_item in song_history_list:
        if history_item.get('title') == new_title and history_item.get('artist') == new_artist:
            cached_image_path_str = history_item.get('image_path')
            if cached_image_path_str:
                cached_image_path = Path(cached_image_path_str)
                if cached_image_path.is_file():
                    logger.info(f"Cache hit found: {cached_image_path}")
                    try:
                        shutil.copy2(cached_image_path, current_display_image_path)
                        logger.info(f"Copied cached image to active path: {current_display_image_path}")
                        image_processed_successfully = True
                        last_image_error_message = "Used Cache"
                        cache_hit = True
                        persistent_path_for_this_song = str(cached_image_path)
                        break
                    except OSError as e:
                        logger.error(f"Failed to copy cached image {cached_image_path} to {current_display_image_path}: {e}")
                    except Exception as e:
                        logger.exception(f"Unexpected error copying cached image: {e}")
                else:
                    logger.warning(f"Cache hit found path {cached_image_path}, but file does not exist.")
            else:
                 logger.warning(f"Cache hit found for song, but history item lacks image path.")
        if cache_hit:
            break

    if not cache_hit:
        logger.info("Cache miss or failed to use cache. Attempting download...")
        images_dict = track_info.get('images', {})
        hq_url = images_dict.get('coverarthq')
        std_url = images_dict.get('coverart')
        urls_to_try = [url for url in [hq_url, std_url] if isinstance(url, str) and url.startswith('http')]
        network_timeout = config['network']['timeout']
        max_retries = config['network']['retry_count']
        retry_delay = config['network']['retry_delay']
        last_image_error_message = "No Cover Art URL"

        if not urls_to_try:
            logger.warning("No valid cover art URLs found for download.")
        else:
            for url in urls_to_try:
                logger.info(f"Attempting image download from URL: {url}")
                for attempt in range(max_retries):
                    if recognition_thread_stop_event.is_set():
                        logger.info("Image download cancelled by shutdown.")
                        last_image_error_message = "Download Cancelled"
                        image_processed_successfully = False
                        break

                    logger.debug(f"  Download attempt {attempt + 1}/{max_retries}...")
                    try:
                        response = requests.get(url, timeout=network_timeout, stream=True)
                        response.raise_for_status()

                        with open(TEMP_IMAGE_PATH, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192): f.write(chunk)

                        if TEMP_IMAGE_PATH.stat().st_size > 0:
                            try:
                                with Image.open(TEMP_IMAGE_PATH) as img_verify: img_verify.verify()
                                os.replace(TEMP_IMAGE_PATH, current_display_image_path)
                                logger.info(f"Image downloaded and updated successfully (Attempt {attempt+1}) using URL: {url}")
                                image_processed_successfully = True
                                last_image_error_message = ""
                                break
                            except (Image.UnidentifiedImageError, SyntaxError, TypeError, ValueError) as verify_e:
                                last_image_error_message = f"Downloaded file invalid ({verify_e.__class__.__name__})"
                                logger.error(f"  {last_image_error_message} from {url} (Attempt {attempt+1})")
                                safe_remove(TEMP_IMAGE_PATH, "invalid downloaded image")
                        else:
                            last_image_error_message = "Downloaded Image Empty"
                            logger.error(f"  {last_image_error_message} for URL {url} (Attempt {attempt+1})")
                            safe_remove(TEMP_IMAGE_PATH, "empty downloaded image")

                    except requests.exceptions.Timeout:
                         last_image_error_message = "Download Timeout"
                         logger.warning(f"  {last_image_error_message} for {url} (Attempt {attempt+1}, timeout={network_timeout}s)")
                    except requests.exceptions.RequestException as e:
                         last_image_error_message = f"Download Failed ({e.__class__.__name__})"
                         logger.warning(f"  {last_image_error_message} for {url} (Attempt {attempt+1}): {e}")
                    except Exception as e:
                         last_image_error_message = f"Unknown Image Error ({e.__class__.__name__})"
                         logger.exception(f"  {last_image_error_message} during download/processing for {url} (Attempt {attempt+1}): {e}")
                    finally:
                        safe_remove(TEMP_IMAGE_PATH, "temp image after download attempt")

                    if image_processed_successfully:
                        break

                    if attempt < max_retries - 1 and not recognition_thread_stop_event.is_set():
                        logger.debug(f"  Waiting {retry_delay}s before next download attempt...")
                        try:
                            await asyncio.sleep(retry_delay)
                        except asyncio.CancelledError:
                             logger.info("Image download sleep cancelled.")
                             last_image_error_message = "Download Cancelled"
                             break

                if image_processed_successfully or recognition_thread_stop_event.is_set():
                    break

            if not image_processed_successfully and not last_image_error_message:
                 last_image_error_message = "Image Download Failed (Unknown Reason)"

    final_persistent_path = None

    if image_processed_successfully and current_display_image_path.is_file():
        logger.debug(f"Adding to history using valid active image: {current_display_image_path}")
        final_persistent_path = add_to_history(new_title, new_artist, new_album, current_display_image_path)
        if final_persistent_path:
            logger.debug(f"Song added/updated in history. Persistent path: {final_persistent_path}")
        else:
            logger.error("add_to_history returned None despite processed image. State might be inconsistent.")
    elif not image_processed_successfully:
        logger.warning("Image download/cache failed. Not adding entry to history cache.")
    else:
        logger.warning("No valid display image path available despite image_processed_successfully=True.")

    path_to_save = persistent_path_for_this_song if cache_hit else final_persistent_path
    save_last_state(new_title, new_artist, new_album, path_to_save)
    prepare_lyrics_for_track(result, new_title, new_artist, record_start_monotonic)
    new_track_key = build_track_key(new_title, new_artist)
    if previous_track_key and new_track_key != previous_track_key:
        schedule_gui_update(begin_track_change_choreography, previous_accent)

    return {
        'status': 'success',
        'title': new_title,
        'album': new_album,
        'artist': new_artist,
        'persistent_path': path_to_save,
        'image_updated': image_processed_successfully,
        'message': last_image_error_message
    }


async def periodic_recognition_task(stop_event: threading.Event):
    """The main async loop: record -> recognize -> process -> schedule update -> wait."""
    interval_seconds = config['gui']['update_interval_ms'] / 1000.0
    wait_chunk = 0.1

    while not stop_event.is_set():
        logger.info("--- Starting New Recognition Cycle ---")
        update_data = {'status': 'error', 'message': 'Cycle Interrupted'}
        wav_file_path = None
        try:
            recognition_cfg = config.get('recognition', {})
            capture_attempts = max(1, int(recognition_cfg.get('capture_attempts_per_cycle', 1)))
            retry_delay_seconds = max(0.0, (safe_float(recognition_cfg.get('retry_delay_ms')) or 0.0) / 1000.0)
            use_extended_recording = bool(recognition_cfg.get('use_extended_recording_on_retry', True))
            extended_record_seconds = safe_float(recognition_cfg.get('extended_record_seconds'))
            base_record_seconds = safe_float(config['audio'].get('record_seconds')) or 4.0

            for capture_attempt in range(capture_attempts):
                if stop_event.is_set():
                    update_data = {'status': 'error', 'message': 'Shutdown'}
                    break

                record_seconds = base_record_seconds
                if capture_attempt > 0 and use_extended_recording and extended_record_seconds:
                    record_seconds = max(base_record_seconds, extended_record_seconds)

                if capture_attempt > 0:
                    logger.info(
                        f"Recognition retry capture {capture_attempt + 1}/{capture_attempts} "
                        f"with {record_seconds:.1f}s sample."
                    )
                    schedule_gui_update(
                        set_status_message,
                        f"Retry capture {capture_attempt + 1}/{capture_attempts}..."
                    )

                wav_file_path, record_start_monotonic = record_audio(record_seconds_override=record_seconds)

                if not wav_file_path:
                    if not stop_event.is_set():
                        logger.warning("Recording failed or produced no file.")
                        update_data = {'status': 'error', 'message': current_status_message}
                    else:
                        logger.info("Stop event detected after record_audio.")
                        update_data = {'status': 'error', 'message': 'Shutdown'}
                    break

                shazam_result = await recognize_song(wav_file_path)
                safe_remove(wav_file_path, "temp WAV after recognition attempt")
                wav_file_path = None

                if stop_event.is_set():
                    logger.info("Stop event detected after recognize_song.")
                    update_data = {'status': 'error', 'message': 'Shutdown'}
                    break

                if shazam_result:
                    if 'track' in shazam_result and shazam_result.get('track'):
                        update_data = await process_recognition_result(shazam_result, record_start_monotonic)
                        break

                    if 'matches' in shazam_result and not shazam_result.get('matches'):
                        if capture_attempt < (capture_attempts - 1):
                            logger.info(
                                f"No match on capture {capture_attempt + 1}/{capture_attempts}; "
                                "trying a fresh recording."
                            )
                            if retry_delay_seconds > 0:
                                await asyncio.sleep(retry_delay_seconds)
                            continue

                        update_data = {'status': 'no_match', 'message': 'No Match Found'}
                        break

                    logger.error(f"Unexpected Shazam result format or empty track: {shazam_result}")
                    update_data = {'status': 'error', 'message': 'Bad Shazam Result'}
                    break

                if capture_attempt < (capture_attempts - 1):
                    logger.info(
                        f"Recognition attempt {capture_attempt + 1}/{capture_attempts} did not return a result; "
                        "trying again with a fresh recording."
                    )
                    if retry_delay_seconds > 0:
                        await asyncio.sleep(retry_delay_seconds)
                    continue

                update_data = {'status': 'error', 'message': current_status_message}

        except Exception as e:
             logger.exception(f"Unhandled error in recognition cycle: {e}")
             update_data = {'status': 'error', 'message': 'Cycle Failed Unexpectedly'}
        finally:
            safe_remove(wav_file_path, "temp WAV after cycle")

            if not stop_event.is_set():
                logger.debug(f"Scheduling GUI update with data: {update_data}")
                schedule_gui_update(update_gui, update_data)
            else:
                logger.info("Stop event set, skipping final GUI update for this cycle.")

        if not stop_event.is_set():
             logger.debug(f"Waiting {interval_seconds:.1f}s for next cycle...")
             start_wait = asyncio.get_event_loop().time()
             while (asyncio.get_event_loop().time() - start_wait) < interval_seconds:
                 if stop_event.is_set():
                     logger.info("Wait interrupted by stop event.")
                     break
                 try:
                     await asyncio.sleep(wait_chunk)
                 except asyncio.CancelledError:
                     logger.info("Waiting sleep cancelled.")
                     break
        else:
             logger.info("Stop event set, exiting recognition loop.")

    logger.info("Periodic recognition task finished.")


def recognition_loop_runner(stop_event: threading.Event):
    """Sets up and runs the asyncio event loop for the background thread."""
    logger.info("Recognition thread starting.")
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(periodic_recognition_task(stop_event))
    except Exception as e:
        logger.exception(f"Exception in recognition thread runner: {e}")
    finally:
        if loop and not loop.is_closed():
             logger.info("Closing asyncio loop in recognition thread.")
             try:
                  tasks = asyncio.all_tasks(loop)
                  if tasks:
                     logger.debug(f"Cancelling {len(tasks)} outstanding tasks...")
                     for task in tasks: task.cancel()
                     loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                     logger.debug("Outstanding tasks cancelled.")
                  logger.debug("Shutting down async generators...")
                  loop.run_until_complete(loop.shutdown_asyncgens())
                  logger.debug("Async generators shutdown.")
             except Exception as cleanup_e:
                  logger.error(f"Error during asyncio task cleanup: {cleanup_e}")
             finally:
                 try:
                     loop.close()
                     logger.info("Asyncio loop closed.")
                 except Exception as close_e:
                     logger.error(f"Error closing asyncio loop: {close_e}")
        logger.info("Recognition thread finished.")


def start_recognition_thread():
    """Creates and starts the background thread for song recognition."""
    global recognition_thread
    if recognition_thread and recognition_thread.is_alive():
        logger.warning("Recognition thread already running. Skipping start.")
        return
    recognition_thread_stop_event.clear()
    recognition_thread = threading.Thread(
        target=recognition_loop_runner,
        args=(recognition_thread_stop_event,),
        name="RecognitionThread",
        daemon=True
    )
    recognition_thread.start()
    logger.info("Recognition thread initiated.")


# --- Main Execution ---
def write_history_separator():
     """Writes a separator line to the history log file if it exists and is not empty."""
     if SONG_HISTORY_FILE_PATH.is_file() and SONG_HISTORY_FILE_PATH.stat().st_size > 0:
          try:
               with open(SONG_HISTORY_FILE_PATH, 'a', encoding='utf-8') as f:
                    f.write(f"\n--- New Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
               logger.info(f"Wrote session separator to {SONG_HISTORY_FILE_PATH}")
          except IOError as e:
               logger.error(f"Could not write session separator to history log: {e}")
     else:
          logger.debug("History log file doesn't exist or is empty. Skipping separator.")


def main():
    global root, canvas, config, title_label_id, album_label_id, artist_label_id, status_label_id, coverart_item_id
    global lyrics_primary_label_id, lyrics_secondary_label_id, lyrics_tertiary_label_id

    config = load_config()
    logger.info("--- Song Recognition Application Starting ---")
    global lyrics_cache
    lyrics_cache = load_lyrics_cache()
    if lyrics_cache:
        logger.info(f"Loaded lyrics cache: {len(lyrics_cache)} entries.")
    load_history_state()
    write_history_separator()

    root = tk.Tk()
    root.title("Song Recognition")
    root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

    restored = load_last_state()
    if not restored:
         logger.info("Starting with empty state or failed restore.")
         if not IMAGE_PATH.is_file():
              create_placeholder_image(IMAGE_PATH, 500, 500, "Play a song!")
         if current_status_message == "Play a song!":
             set_status_message("Ready")

    initial_width = 800
    initial_height = 600
    start_fullscreen = False

    root.geometry(f"{initial_width}x{initial_height}")
    root.update_idletasks()

    if start_fullscreen:
        toggle_fullscreen()
        logger.info(f"Attempting to start fullscreen.")
    else:
        logger.info(f"Starting windowed: {initial_width}x{initial_height}")

    canvas = tk.Canvas(root, bg="#0a0a0c", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=tk.YES)

    # Warm the font cache now that Tk is up.
    get_ui_font_family()

    title_label_id = None
    album_label_id = None
    artist_label_id = None
    status_label_id = None
    coverart_item_id = None
    lyrics_primary_label_id = None
    lyrics_secondary_label_id = None
    lyrics_tertiary_label_id = None

    root.bind("<Escape>", toggle_fullscreen)
    root.bind("<Motion>", reset_cursor_hide_timer)
    root.bind("<Configure>", on_resize)
    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.update()
    root.after(100, trigger_full_redraw)
    root.after(100, reset_cursor_hide_timer)
    root.after(300, tick_status_pulse)
    root.after(400, tick_lyric_glow)
    root.after(600, tick_ken_burns)

    start_recognition_thread()

    logger.info("Starting Tkinter main loop.")
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected. Initiating shutdown.")
        on_closing()
    except Exception as e:
         logger.exception("Unhandled exception in Tkinter main loop.")
         on_closing()

    logger.info("--- Song Recognition Application Exited ---")

if __name__ == "__main__":
    main()
# --- END OF FILE shazam.py ---
