"""
Text pasting functionality for MySuperWhisper.
Uses direct text injection when available, with an optional clipboard mode.
"""

import os
import subprocess
import time
import shutil
import pyperclip
from .config import log, config


_YDOTOOL_KEY_DELAY_MS = 15


def detect_session_type():
    """Detect if running on Wayland or X11."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower()


def _has_command(name):
    """Check whether a command is available."""
    return shutil.which(name) is not None


def _is_terminal(session_type):
    """
    Check if the active window is a terminal emulator.
    Uses xdotool/xprop on X11 and compatible Wayland environments.
    """
    try:
        cmd_id = ["xdotool", "getactivewindow"]
        result_id = subprocess.run(cmd_id, capture_output=True, text=True, timeout=0.5)

        if result_id.returncode != 0:
            return False

        window_id = result_id.stdout.strip()
        if not window_id:
            return False

        cmd_prop = ["xprop", "-id", window_id, "WM_CLASS"]
        result_prop = subprocess.run(cmd_prop, capture_output=True, text=True, timeout=0.5)

        if result_prop.returncode != 0:
            return False

        class_info = result_prop.stdout.lower()
        return "term" in class_info or "console" in class_info or "kitty" in class_info

    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False


def paste_text(text, press_enter=False):
    """
    Insert text into the active application.

    Direct typing is the default and preserves the clipboard. On Wayland,
    ydotool is preferred, with wtype as a fallback. Enable clipboard mode for
    applications that need clipboard-based Unicode insertion.
    """
    session_type = detect_session_type()

    if not config.use_clipboard_to_paste:
        typed = False
        if _has_command("ydotool"):
            typed = _inject_text_with_ydotool(text)
            if not typed:
                log("ydotool text injection failed; trying the session typing tool", "warning")

        if not typed:
            typed = _type_text(text, session_type)

        if not typed:
            log(
                "Direct text injection failed; enable clipboard paste from the tray menu to use the clipboard.",
                "error",
            )
            return

        if press_enter:
            time.sleep(0.05)
            _press_key("Return", session_type)
        return

    if _is_terminal(session_type):
        _paste_clipboard(text, session_type, force_ctrl_shift_v=True)
    elif "\n" in text:
        _paste_with_newlines(text, session_type)
    else:
        _paste_clipboard(text, session_type)

    if press_enter:
        time.sleep(0.05)
        _press_key("Return", session_type)


def _inject_text_with_ydotool(text):
    """Inject text using ydotool, which works reliably on Wayland."""
    try:
        result = subprocess.run(
            ["ydotool", "type", "--key-delay", str(_YDOTOOL_KEY_DELAY_MS), text],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True

        stderr = result.stderr.strip() or "unknown error"
        log(f"ydotool injection failed: {stderr}", "warning")
        return False
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        log("ydotool injection timed out", "warning")
        return False
    except Exception as exc:
        log(f"ydotool injection error: {exc}", "warning")
        return False


def _paste_clipboard(text, session_type, force_ctrl_shift_v=False):
    """Paste text using the system clipboard and the session paste shortcut."""
    pyperclip.copy(text)
    time.sleep(0.05)

    if session_type == "wayland":
        key_codes = (
            ["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]
            if force_ctrl_shift_v
            else ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]
        )
        if _has_command("ydotool"):
            try:
                subprocess.run(key_codes, check=True, timeout=5)
                return
            except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
                log(f"ydotool paste shortcut failed; trying wtype: {exc}", "warning")

        if force_ctrl_shift_v:
            wtype_command = [
                "wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl"
            ]
        else:
            wtype_command = ["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"]
        try:
            subprocess.run(wtype_command, check=True, timeout=5)
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            log(f"Wayland paste shortcut failed: {exc}", "error")
        return

    key_combo = "ctrl+shift+v" if force_ctrl_shift_v else "ctrl+v"
    try:
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", key_combo],
            check=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        log(f"X11 paste shortcut failed: {exc}", "error")


def _paste_with_newlines(text, session_type):
    """Paste text with newlines, using Shift+Return for soft breaks."""
    lines = text.split("\n")

    for index, line in enumerate(lines):
        if line:
            _paste_clipboard(line, session_type)

        if index < len(lines) - 1:
            time.sleep(0.03)
            _press_key("shift+Return", session_type)
            time.sleep(0.02)


def _type_text(text, session_type):
    """Type text directly without changing the system clipboard."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line:
            if session_type == "wayland":
                command = ["wtype", "--", line]
            else:
                command = ["xdotool", "type", "--clearmodifiers", "--", line]
            try:
                subprocess.run(command, check=True, timeout=60)
            except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
                log(f"Direct typing failed: {exc}", "error")
                return False

        if index < len(lines) - 1:
            time.sleep(0.03)
            _press_key("shift+Return", session_type)
            time.sleep(0.02)

    return True


def _press_key(key, session_type):
    """Press a key or key combination, falling back from ydotool if needed."""
    if _has_command("ydotool") and key in ("Return", "shift+Return"):
        if key == "Return":
            ydotool_command = ["ydotool", "key", "28:1", "28:0"]
        else:
            ydotool_command = ["ydotool", "key", "42:1", "28:1", "28:0", "42:0"]
        try:
            subprocess.run(ydotool_command, check=True, timeout=5)
            return
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            log(f"ydotool key press failed; trying the session tool: {exc}", "warning")

    try:
        if session_type == "wayland":
            if "+" in key:
                modifier, keyname = key.split("+", 1)
                command = ["wtype", "-M", modifier.lower(), "-k", keyname, "-m", modifier.lower()]
            else:
                command = ["wtype", "-k", key]
        else:
            command = ["xdotool", "key", "--clearmodifiers", key]
        subprocess.run(command, check=True, timeout=5)
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        log(f"Key press failed: {exc}", "error")


def press_enter_key():
    """Simulate pressing the Enter key."""
    session_type = detect_session_type()
    _press_key("Return", session_type)
