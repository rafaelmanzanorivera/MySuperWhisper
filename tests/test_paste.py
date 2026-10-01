"""Tests for paste behavior, focused on the clipboard vs direct-typing routing."""

from unittest.mock import patch

import mysuperwhisper.paste as paste
from mysuperwhisper.config import Config, config


def _flatten_calls(mock_run):
    """Return the list of argv lists passed to subprocess.run."""
    return [c.args[0] for c in mock_run.call_args_list if c.args]


def test_use_clipboard_to_paste_defaults_to_false():
    """By default we preserve the clipboard (direct typing)."""
    assert Config().use_clipboard_to_paste is False


def test_direct_type_does_not_touch_clipboard():
    """When clipboard paste is disabled, the clipboard must stay untouched."""
    config.use_clipboard_to_paste = False
    with patch.object(paste, "detect_session_type", return_value="x11"), \
         patch.object(paste, "_has_command", return_value=False), \
         patch.object(paste.subprocess, "run") as mock_run, \
         patch.object(paste.pyperclip, "copy") as mock_copy:
        paste.paste_text("hello")

    mock_copy.assert_not_called()
    argvs = _flatten_calls(mock_run)
    assert ["xdotool", "type", "--clearmodifiers", "--", "hello"] in argvs


def test_direct_type_uses_wtype_on_wayland():
    config.use_clipboard_to_paste = False
    with patch.object(paste, "detect_session_type", return_value="wayland"), \
         patch.object(paste, "_has_command", return_value=False), \
         patch.object(paste.subprocess, "run") as mock_run, \
         patch.object(paste.pyperclip, "copy") as mock_copy:
        paste.paste_text("hello")

    mock_copy.assert_not_called()
    argvs = _flatten_calls(mock_run)
    assert ["wtype", "--", "hello"] in argvs


def test_direct_type_multiline_uses_soft_returns():
    """Newlines become Shift+Return so chat apps don't submit early."""
    config.use_clipboard_to_paste = False
    with patch.object(paste, "detect_session_type", return_value="x11"), \
         patch.object(paste, "_has_command", return_value=False), \
         patch.object(paste.subprocess, "run") as mock_run, \
         patch.object(paste.pyperclip, "copy"):
        paste.paste_text("line1\nline2")

    argvs = _flatten_calls(mock_run)
    assert ["xdotool", "type", "--clearmodifiers", "--", "line1"] in argvs
    assert ["xdotool", "type", "--clearmodifiers", "--", "line2"] in argvs
    # A soft break (Shift+Return) is emitted between the two lines.
    assert ["xdotool", "key", "--clearmodifiers", "shift+Return"] in argvs


def test_clipboard_mode_still_copies():
    """Regression: with the option on, the legacy clipboard paste is used."""
    config.use_clipboard_to_paste = True
    with patch.object(paste, "detect_session_type", return_value="x11"), \
         patch.object(paste, "_is_terminal", return_value=False), \
         patch.object(paste.subprocess, "run") as mock_run, \
         patch.object(paste.pyperclip, "copy") as mock_copy:
        paste.paste_text("hello")

    mock_copy.assert_called_once_with("hello")
    argvs = _flatten_calls(mock_run)
    assert ["xdotool", "key", "--clearmodifiers", "ctrl+v"] in argvs
