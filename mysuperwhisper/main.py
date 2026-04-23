#!/usr/bin/env python3
"""
MySuperWhisper - Global Voice Dictation Tool

A Linux desktop application that provides global voice-to-text transcription
using OpenAI's Whisper model. Press Double Ctrl to start/stop recording,
and the transcribed text is automatically typed into any application.

Features:
- Global hotkey (Double Ctrl) works in any application
- Supports multiple Whisper model sizes (tiny to large-v3)
- GPU acceleration with INT8 quantization
- Voice commands for newlines and validation
- Transcription history with Triple Ctrl
- System tray integration
- Multi-language support for voice commands (FR/EN/ES)

Usage:
    python -m mysuperwhisper
    python -m mysuperwhisper --playback  # Debug mode with audio playback

Author: Olivier Mary
License: MIT
"""

import sys
# Hack to access system PyGObject (gi) from venv for AppIndicator support
sys.path.append('/usr/lib/python3/dist-packages')

import argparse
import os
import queue
import threading
import time

from .config import (
    log, config, LOG_FILE, CONFIG_DIR, LOCK_FILE, CONTROL_SOCKET,
    EFFECTIVE_HOME, EFFECTIVE_USER
)
from . import audio
from . import transcription
from . import history
from .control import ControlServer, send_command
from .voice_commands import process_voice_commands
from .paste import paste_text, press_enter_key
from .notifications import send_notification, play_sound


# Processing queue
processing_queue = queue.Queue()

# Command line arguments
args = None
control_server = None


class _NullTray:
    """No-op tray used when the real tray backend is unavailable."""

    _tray_icon = None

    def update_tray(self, status, level=0.0):
        return None

    def set_callbacks(self, on_quit, save_config):
        return None

    def create_tray_icon(self):
        raise RuntimeError("Tray backend is unavailable")

    def run_tray(self):
        return None

    def device_monitor_worker(self):
        return None


tray = _NullTray()


class _NullKeyboard:
    """No-op keyboard backend used when pynput is not loaded."""

    def set_callbacks(self, on_record_hotkey, on_history_hotkey, is_recording):
        return None

    def start_listener(self):
        return None


keyboard = _NullKeyboard()


def load_tray_module():
    """Import the tray module only when needed."""
    global tray
    if not isinstance(tray, _NullTray):
        return True, None

    try:
        from . import tray as real_tray
        tray = real_tray
        return True, None
    except Exception as exc:
        tray = _NullTray()
        return False, exc


def load_keyboard_module():
    """Import the keyboard module only when needed."""
    global keyboard
    if not isinstance(keyboard, _NullKeyboard):
        return True, None

    try:
        from . import keyboard as real_keyboard
        keyboard = real_keyboard
        return True, None
    except Exception as exc:
        keyboard = _NullKeyboard()
        return False, exc


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Global Voice Dictation Tool")
    parser.add_argument(
        "--playback",
        action="store_true",
        help="Enable audio playback after recording (debug)"
    )
    parser.add_argument(
        "--no-tray",
        "--headless",
        dest="no_tray",
        action="store_true",
        help="Run without the system tray"
    )
    parser.add_argument(
        "--toggle-recording",
        action="store_true",
        help="Ask the running instance to start or stop recording"
    )
    parser.add_argument(
        "--show-history",
        action="store_true",
        help="Ask the running instance to open the history popup"
    )
    parser.add_argument(
        "--quit",
        action="store_true",
        help="Ask the running instance to quit"
    )
    parser.add_argument(
        "--enable-pynput-hotkeys",
        action="store_true",
        help="Force the internal pynput global hotkey listener on Wayland"
    )
    return parser.parse_args()


def on_double_ctrl():
    """Handle Double Ctrl: toggle recording."""
    if audio.is_currently_recording():
        stop_and_process()
    else:
        start_recording()


def on_triple_ctrl():
    """Handle Triple Ctrl: open history popup."""
    if not history.is_popup_open():
        history.open_history_popup_async()


def start_recording():
    """Start voice recording."""
    audio.start_recording()
    tray.update_tray("recording")

    # Notifications
    play_sound("start")
    send_notification(
        "MySuperWhisper",
        "Recording...",
        "audio-input-microphone"
    )


def stop_and_process():
    """Stop recording and queue audio for processing."""
    audio_data = audio.stop_recording()

    # Immediate feedback sound
    play_sound("success")

    if audio_data is None:
        play_sound("error")
        tray.update_tray("idle")
        return

    tray.update_tray("processing")
    processing_queue.put(audio_data)


def audio_processing_loop():
    """
    Main processing loop running in a separate thread.
    Handles transcription and text pasting.
    """
    while True:
        # Wait for audio data
        audio_data = processing_queue.get()

        # Optional debug playback
        if args and args.playback:
            log("Debug playback...", "debug")
            try:
                import sounddevice as sd
                sd.play(audio_data, audio.SAMPLE_RATE)  # Uses PulseAudio default
                sd.wait()
            except Exception as e:
                log(f"Playback error: {e}", "error")

        log("Transcribing...")

        # Prepare audio for Whisper (downsample to 16kHz)
        audio_16k = audio.prepare_for_whisper(audio_data)

        try:
            # Transcribe
            text = transcription.transcribe(audio_16k, language=config.language, task=config.task)

            if text:
                log(f"Raw transcription: '{text}'")

                # Process voice commands
                processed_text, should_validate = process_voice_commands(text)
                log(f"After command processing: '{processed_text}' (validate={should_validate})")

                if processed_text:
                    # Paste the text
                    paste_text(processed_text, press_enter=should_validate)

                    # Add to history (original text)
                    history.add_to_history(text)

                    # Success notification
                    send_notification(
                        "MySuperWhisper",
                        f"Text pasted ({len(processed_text)} chars)",
                        "dialog-ok"
                    )
                elif should_validate:
                    # Just validation keyword without text -> press Enter
                    press_enter_key()
                    send_notification(
                        "MySuperWhisper",
                        "Enter key sent",
                        "dialog-ok"
                    )
            else:
                log("Nothing detected.", "warning")
                play_sound("error")
                send_notification(
                    "MySuperWhisper",
                    "No text detected",
                    "dialog-warning"
                )

        except Exception as e:
            log(f"Transcription error: {e}", "error")
            play_sound("error")
            send_notification(
                "MySuperWhisper",
                f"Error: {e}",
                "dialog-error"
            )

        # Return to idle state
        tray.update_tray("idle")


def save_config():
    """Save configuration."""
    config.save()


def startup_worker():
    """
    Startup initialization running in background.
    Loads model and starts audio stream.
    """
    # Load Whisper model
    transcription.load_model()

    # Start audio processing thread
    processing_thread = threading.Thread(target=audio_processing_loop, daemon=True)
    processing_thread.start()

    # Start audio stream (uses PulseAudio default source)
    audio.start_stream()

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    hotkeys_enabled = session_type != "wayland" or args.enable_pynput_hotkeys

    if hotkeys_enabled:
        loaded, keyboard_error = load_keyboard_module()
        if not loaded:
            log(f"Global hotkey listener unavailable: {keyboard_error}", "warning")
            log_wayland_shortcut_help()
        else:
            keyboard.set_callbacks(
                on_record_hotkey=on_double_ctrl,
                on_history_hotkey=on_triple_ctrl,
                is_recording=audio.is_currently_recording
            )
            keyboard.start_listener()
            hotkey_desc = f"{config.record_press_count}x {config.record_hotkey}"
            if loaded:
                from .keyboard import _get_hotkey_description
                hotkey_desc = _get_hotkey_description(config.record_hotkey, config.record_press_count)
            log(f"Ready! Press {hotkey_desc} to start/stop recording.")
    else:
        log("Wayland session detected: internal pynput global hotkeys are disabled by default.")
        log_wayland_shortcut_help()

    if not args.no_tray and tray._tray_icon is not None:
        log("The icon has been added to the notification area (system tray).")
        log("Right-click the icon to change microphone or test audio level.")
        threading.Thread(target=tray_status_monitor_worker, daemon=True).start()
    else:
        log("Running without tray UI.")

    tray.update_tray("idle")


def on_quit():
    """Handle application quit."""
    global control_server
    if control_server:
        control_server.close()
    os._exit(0)


def tray_status_monitor_worker():
    """Keep the tray state aligned with the actual recording state."""
    while True:
        time.sleep(0.5)
        try:
            if args and args.no_tray:
                continue
            if getattr(tray, "_tray_icon", None) is None:
                continue
            current_status = getattr(tray, "get_tray_status", lambda: None)()
            if current_status == "recording" and not audio.is_currently_recording():
                log("Tray status was stale (recording while audio was idle); resetting to idle.", "warning")
                tray.update_tray("idle")
        except Exception as exc:
            log(f"Tray status monitor error: {exc}", "debug")


def log_wayland_shortcut_help():
    """Log the recommended Wayland shortcut integration."""
    command_prefix = f"{sys.executable} -m mysuperwhisper"
    log(
        "Use GNOME custom shortcuts on Wayland instead of pynput. "
        f"Record toggle: {command_prefix} --toggle-recording"
    )
    log(
        f"History popup: {command_prefix} --show-history"
    )


def _pid_exists(pid):
    """Check whether a process exists."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _acquire_lock(lock_path):
    """Try to acquire the instance lock."""
    import fcntl

    lock_handle = open(lock_path, 'a+')
    fcntl.lockf(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(str(os.getpid()))
    lock_handle.flush()
    return lock_handle


def check_single_instance():
    """
    Ensure only one instance is running using lock file.
    Returns True if this is the only instance, False otherwise.
    """
    global _instance_lock_file
    lock_file = str(LOCK_FILE)

    try:
        f = _acquire_lock(lock_file)
        _instance_lock_file = f
        return True
    except OSError:
        try:
            with open(lock_file, 'r') as existing:
                content = existing.read().strip()
            pid = int(content) if content else 0
        except (OSError, ValueError):
            pid = 0

        if pid and not _pid_exists(pid):
            log(f"Removing stale lock file for dead PID {pid}", "warning")
            try:
                os.unlink(lock_file)
            except OSError:
                pass
            try:
                f = _acquire_lock(lock_file)
                _instance_lock_file = f
                return True
            except OSError:
                return False

        return False


def handle_remote_command(parsed_args):
    """Forward a control command to the running instance."""
    command = None
    if parsed_args.toggle_recording:
        command = "toggle-recording"
    elif parsed_args.show_history:
        command = "show-history"
    elif parsed_args.quit:
        command = "quit"

    if not command:
        return False

    ok, message = send_command(CONTROL_SOCKET, command)
    if ok:
        log(f"Delivered control command: {command}")
        return True

    print(message)
    sys.exit(1)


def run_without_tray():
    """Keep the process alive when the tray is disabled."""
    while True:
        time.sleep(3600)


def main():
    """Main entry point."""
    global args, control_server

    # Parse arguments
    args = parse_args()

    if handle_remote_command(args):
        return

    # Check for existing instance
    if not check_single_instance():
        print("MySuperWhisper is already running!")
        send_notification("MySuperWhisper", "Application is already running.", "dialog-information")
        sys.exit(0)

    log("Starting MySuperWhisper")
    log(f"Config directory: {CONFIG_DIR}")
    log(f"Log file: {LOG_FILE}")
    log(f"Effective user directory owner: {EFFECTIVE_USER} ({EFFECTIVE_HOME})")

    # Load configuration
    config.load()

    # Restore PulseAudio devices from config
    config.restore_audio_devices()

    # Load history
    history.load_history()

    control_server = ControlServer(
        CONTROL_SOCKET,
        {
            "toggle-recording": on_double_ctrl,
            "show-history": on_triple_ctrl,
            "quit": on_quit,
        },
        log,
    )
    try:
        control_server.start()
    except Exception as exc:
        log(f"Control channel unavailable at {CONTROL_SOCKET}: {exc}", "warning")
        log("Command-based remote control is disabled for this session.", "warning")
        control_server = None

    # Setup tray callbacks
    tray.set_callbacks(on_quit=on_quit, save_config=save_config)

    tray_enabled = not args.no_tray
    if tray_enabled:
        loaded, tray_error = load_tray_module()
        if not loaded:
            log(f"Tray backend could not be loaded, continuing without it: {tray_error}", "warning")
            tray_enabled = False
            args.no_tray = True
        else:
            try:
                tray.create_tray_icon()
            except Exception as exc:
                log(f"Tray unavailable, continuing without it: {exc}", "warning")
                tray_enabled = False
                args.no_tray = True

    # Start background initialization
    threading.Thread(target=startup_worker, daemon=True).start()

    if tray_enabled:
        # Start device monitoring
        threading.Thread(target=tray.device_monitor_worker, daemon=True).start()

        # Run tray event loop (blocking)
        try:
            tray.run_tray()
        except Exception as exc:
            log(f"Tray event loop failed, continuing headless: {exc}", "warning")
            run_without_tray()
    else:
        run_without_tray()


if __name__ == "__main__":
    main()
