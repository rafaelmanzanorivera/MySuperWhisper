"""
Configuration management for MySuperWhisper.
Handles loading/saving settings and XDG directory setup.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import pwd
import tempfile
from pathlib import Path
import sys

APP_NAME = "mysuperwhisper"


def _resolve_effective_user():
    """Resolve the user whose XDG directories should be used."""
    sudo_user = os.environ.get("SUDO_USER")
    if os.geteuid() == 0 and sudo_user and sudo_user != "root":
        try:
            entry = pwd.getpwnam(sudo_user)
            return sudo_user, entry.pw_uid, Path(entry.pw_dir)
        except KeyError:
            pass

    home = Path.home()
    return os.environ.get("USER", str(os.geteuid())), os.geteuid(), home


EFFECTIVE_USER, EFFECTIVE_UID, EFFECTIVE_HOME = _resolve_effective_user()


def _resolve_app_dirs():
    """Resolve config, data, and runtime directories."""
    home_override = os.environ.get("MYSUPERWHISPER_HOME")
    config_override = os.environ.get("MYSUPERWHISPER_CONFIG_HOME")
    data_override = os.environ.get("MYSUPERWHISPER_DATA_HOME")
    root_via_sudo = os.geteuid() == 0 and os.environ.get("SUDO_USER")

    if home_override:
        base_home = Path(home_override).expanduser()
        config_base = base_home / ".config"
        data_base = base_home / ".local" / "share"
    else:
        config_env = os.environ.get("XDG_CONFIG_HOME") if not root_via_sudo else None
        data_env = os.environ.get("XDG_DATA_HOME") if not root_via_sudo else None
        config_base = Path(config_env).expanduser() if config_env else EFFECTIVE_HOME / ".config"
        data_base = Path(data_env).expanduser() if data_env else EFFECTIVE_HOME / ".local" / "share"

    config_root = Path(config_override).expanduser() if config_override else config_base / APP_NAME
    data_root = Path(data_override).expanduser() if data_override else data_base / APP_NAME

    runtime_env = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_env and os.access(runtime_env, os.W_OK):
        runtime_root = Path(runtime_env) / APP_NAME
    else:
        runtime_root = Path(tempfile.gettempdir()) / f"{APP_NAME}-{EFFECTIVE_UID}"

    return config_root, data_root, runtime_root


# --- XDG Standard Directories ---
CONFIG_DIR, DATA_DIR, RUNTIME_DIR = _resolve_app_dirs()
LOG_DIR = DATA_DIR / "logs"
HISTORY_FILE = DATA_DIR / "history.json"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCK_FILE = RUNTIME_DIR / "instance.lock"
CONTROL_SOCKET = RUNTIME_DIR / "control.sock"


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


for _path in (CONFIG_DIR, DATA_DIR, LOG_DIR, RUNTIME_DIR):
    _ensure_dir(_path)

# --- Logging Configuration ---
LOG_FILE = LOG_DIR / "mysuperwhisper.log"

# Main logger
logger = logging.getLogger("MySuperWhisper")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = False

# Log format
log_format = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# File handler (rotation: 5 files of 1MB max)
try:
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
except OSError:
    fallback_log_dir = _ensure_dir(RUNTIME_DIR / "logs")
    LOG_FILE = fallback_log_dir / "mysuperwhisper.log"
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )

file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_format)
logger.addHandler(file_handler)

# Note: Rotation happens automatically when file reaches 1MB (maxBytes)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)


def log(message, level="info"):
    """Log a message with the specified level."""
    if level == "debug":
        logger.debug(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    else:
        logger.info(message)


class Config:
    """Application configuration singleton."""

    def __init__(self):
        # Default values
        self.model_size = "medium"
        self.language = None  # Auto-detect if None, or use language code like "en", "fr", "es"
        self.task = "transcribe"  # "transcribe" or "translate"
        self.system_notifications_enabled = True
        self.sound_notifications_enabled = True
        self.input_device = None
        self.output_device = None
        # When True, paste via the system clipboard (Ctrl+V). When False (default),
        # type the text directly so the clipboard and its history stay untouched.
        self.use_clipboard_to_paste = False

        # Hotkey configuration
        self.record_hotkey = "ctrl_l"  # Key for recording: "ctrl_l", "alt_r", "ctrl_r", etc.
        self.record_press_count = 2  # Number of presses: 1=single, 2=double, 3=triple
        self.history_hotkey = "ctrl_l"  # Key for history popup
        self.history_press_count = 3  # Number of presses for history

    def load(self):
        """Load configuration from file."""
        needs_save = False
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)

                self.model_size = data.get("model_size", "medium")
                self.language = data.get("language")  # None = auto-detect
                self.task = data.get("task", "transcribe")
                self.system_notifications_enabled = data.get("system_notifications_enabled", True)
                self.sound_notifications_enabled = data.get("sound_notifications_enabled", True)
                self.input_device = data.get("input_device")
                self.output_device = data.get("output_device")
                self.use_clipboard_to_paste = data.get("use_clipboard_to_paste", False)

                # Hotkey configuration
                self.record_hotkey = data.get("record_hotkey", "ctrl_l")
                self.record_press_count = data.get("record_press_count", 2)
                self.history_hotkey = data.get("history_hotkey", "ctrl_l")
                self.history_press_count = data.get("history_press_count", 3)

                log(f"Configuration loaded from {CONFIG_FILE}")
                if self.language:
                    log(f"Language set to: {self.language}")
                log(f"Record hotkey: {self.record_press_count}x {self.record_hotkey}")

                # Check if new fields are missing (for config migration)
                if ("language" not in data or "task" not in data or
                    "record_hotkey" not in data or "record_press_count" not in data or
                    "use_clipboard_to_paste" not in data):
                    log("Updating config file with new fields")
                    needs_save = True
            else:
                log(f"No config file found at {CONFIG_FILE}, creating with defaults")
                needs_save = True
        except Exception as e:
            log(f"Error loading config: {e}", "error")
            needs_save = True

        # Save config if needed (first run or migration)
        if needs_save:
            self.save()

    def save(self):
        """Save configuration to file."""
        try:
            data = {
                "model_size": self.model_size,
                "language": self.language,
                "task": self.task,
                "system_notifications_enabled": self.system_notifications_enabled,
                "sound_notifications_enabled": self.sound_notifications_enabled,
                "input_device": self.input_device,
                "output_device": self.output_device,
                "use_clipboard_to_paste": self.use_clipboard_to_paste,
                "record_hotkey": self.record_hotkey,
                "record_press_count": self.record_press_count,
                "history_hotkey": self.history_hotkey,
                "history_press_count": self.history_press_count
            }

            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)

            log("Configuration saved.")
        except Exception as e:
            log(f"Error saving config: {e}", "error")

    def restore_audio_devices(self):
        """
        Restore audio devices from config.
        Now handled automatically by audio.start_stream() using config.
        """
        pass


# Global config instance
config = Config()
