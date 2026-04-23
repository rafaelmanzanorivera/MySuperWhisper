"""
Text pasting functionality for MySuperWhisper.
Uses direct text injection when available, with clipboard paste fallback.
"""

import os
import subprocess
import time
import shutil
import pyperclip
from .config import log


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
        # 1. Get Active Window ID
        # Note: xdotool might not work on native Wayland windows, 
        # but often works for XWayland or if disabled security.
        cmd_id = ["xdotool", "getactivewindow"]
        result_id = subprocess.run(cmd_id, capture_output=True, text=True, timeout=0.5)
        
        if result_id.returncode != 0:
            return False
            
        window_id = result_id.stdout.strip()
        if not window_id:
            return False

        # 2. Get Window Class
        cmd_prop = ["xprop", "-id", window_id, "WM_CLASS"]
        result_prop = subprocess.run(cmd_prop, capture_output=True, text=True, timeout=0.5)
        
        if result_prop.returncode != 0:
            return False

        # Check for terminal keywords
        # Common classes: gnome-terminal, xterm, kitty, alacritty, konsole...
        class_info = result_prop.stdout.lower()
        return "term" in class_info or "console" in class_info or "kitty" in class_info

    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        # Tools not installed or other error -> assume not terminal
        return False


def paste_text(text, press_enter=False):
    """
    Paste text into the active application using clipboard.

    Strategy:
    1. Copy text to clipboard
    2. Send Ctrl+V to paste (fast, single operation)
    3. Handle newlines with Shift+Return for soft breaks

    Args:
        text: Text to paste
        press_enter: If True, press Enter after pasting
    """
    session_type = detect_session_type()

    if _has_command("ydotool"):
        if _inject_text_with_ydotool(text):
            if press_enter:
                time.sleep(0.05)
                _press_key("Return", session_type)
            return
        log("ydotool text injection failed, falling back to clipboard paste", "warning")
    
    # Check if we are in a terminal
    if _is_terminal(session_type):
        # Terminals (mostly) use Ctrl+Shift+V for paste
        # and handle multiline paste better as a single block.
        _paste_clipboard(text, session_type, force_ctrl_shift_v=True)
    else:
        # Standard GUI App logic
        has_newlines = '\n' in text

        if has_newlines:
            # For text with newlines, paste line by line with Shift+Return
            # This prevents validation in chat apps
            _paste_with_newlines(text, session_type)
        else:
            # Simple text: clipboard paste (Ctrl+V)
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
            timeout=60
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
    except Exception as e:
        log(f"ydotool injection error: {e}", "warning")
        return False


def _paste_clipboard(text, session_type, force_ctrl_shift_v=False):
    """Paste text using clipboard (Ctrl+V or Ctrl+Shift+V)."""
    # Copy to clipboard
    pyperclip.copy(text)
    time.sleep(0.05)  # Slightly increased delay for reliability

    try:
        if session_type == "wayland":
            if force_ctrl_shift_v:
                if _has_command("ydotool"):
                    subprocess.run(["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"])
                else:
                    # Ctrl+Shift+V on Wayland
                    subprocess.run(["wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl"])
            else:
                if _has_command("ydotool"):
                    subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])
                else:
                    # Ctrl+V on Wayland
                    subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"])
        else:
            key_combo = "ctrl+shift+v" if force_ctrl_shift_v else "ctrl+v"
            # X11
            subprocess.run(["xdotool", "key", "--clearmodifiers", key_combo])
            
    except FileNotFoundError as e:
        log(f"Paste tool not found: {e}", "error")


def _paste_with_newlines(text, session_type):
    """Paste text with newlines, using Shift+Return for soft breaks."""
    lines = text.split('\n')

    for i, line in enumerate(lines):
        if line:
            _paste_clipboard(line, session_type)

        # Add soft newline (Shift+Return) between lines
        if i < len(lines) - 1:
            time.sleep(0.03)
            _press_key("shift+Return", session_type)
            time.sleep(0.02)


def _press_key(key, session_type):
    """Press a key or key combination."""
    try:
        if _has_command("ydotool"):
            if key == "Return":
                subprocess.run(["ydotool", "key", "28:1", "28:0"])
                return
            if key == "shift+Return":
                subprocess.run(["ydotool", "key", "42:1", "28:1", "28:0", "42:0"])
                return

        if session_type == "wayland":
            if '+' in key:
                # Handle modifier+key combo (e.g., "shift+Return")
                parts = key.split('+')
                modifier = parts[0].lower()
                keyname = parts[1]
                subprocess.run(["wtype", "-M", modifier, "-k", keyname, "-m", modifier])
            else:
                subprocess.run(["wtype", "-k", key])
        else:
            subprocess.run(["xdotool", "key", "--clearmodifiers", key])
    except FileNotFoundError as e:
        log(f"Key press tool not found: {e}", "error")


def press_enter_key():
    """Simulate pressing the Enter key."""
    session_type = detect_session_type()
    _press_key("Return", session_type)
