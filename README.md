# MySuperWhisper

<p align="center">
  <img src="mysuperwhisper.svg" alt="MySuperWhisper Logo" width="128">
</p>

<p align="center">
  <strong>Global Voice Dictation for Linux using Whisper AI</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#voice-commands">Voice Commands</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#contributing">Contributing</a>
</p>

---

MySuperWhisper is a Linux desktop application that provides **global voice-to-text transcription** using OpenAI's Whisper model. On X11, you can use the built-in global hotkey listener. On GNOME Wayland, the reliable path is to keep the app running in the user session and trigger it through native GNOME custom shortcuts.

This fork is focused on making the GNOME Wayland path practical:
- tray stays optional instead of being required for startup
- global shortcuts are driven by GNOME custom shortcuts instead of `pynput`
- text injection prefers `ydotool`
- CUDA 12 user-space libraries can live inside the project venv

## Features

- 🎤 **Global Hotkey** - Built-in listener on X11, native desktop shortcuts on GNOME Wayland
- 🚀 **GPU Acceleration** - Uses CUDA with INT8 quantization for fast transcription
- 🧠 **Multiple Models** - Choose from tiny to large-v3 based on your needs
- 🗣️ **Voice Commands** - Say "new line" or "enter" to control text formatting
- 📜 **History** - Triple Ctrl opens recent transcriptions for quick re-use
- 📋 **Clipboard-safe typing** - Direct typing is the default; clipboard paste is optional
- 🔔 **Notifications** - Audio beeps and system notifications for feedback
- 🌍 **Multi-language** - Voice commands work in French, English, and Spanish
- 🖥️ **System Tray** - Easy access to settings and device selection

## Requirements

- Linux (X11 or Wayland)
- Python 3.8+
- NVIDIA GPU with CUDA (optional, falls back to CPU)
- PulseAudio or PipeWire

## Installation

### Quick Install (Ubuntu/Debian)

```bash
# Clone the Wayland fork
git clone --branch wayland-gnome-fixes https://github.com/rafaelmanzanorivera/MySuperWhisper.git
cd MySuperWhisper

# Run the installer
chmod +x install.sh
./install.sh
```

### Manual Installation

```bash
# System dependencies (python3-tk is required for history and shortcut dialogs)
sudo apt install python3-venv python3-pip python3-tk xdotool libnotify-bin pulseaudio-utils

# For reliable Linux text injection
sudo apt install ydotool

# Optional clipboard-style Wayland fallback
sudo apt install wtype

# Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### CUDA Runtime In The Venv

If your NVIDIA driver is installed but `faster-whisper` fails on missing `libcublas.so.12`, install the CUDA 12 user-space runtime packages into the project venv:

```bash
./venv/bin/pip install 'nvidia-cublas-cu12' 'nvidia-cudnn-cu12==9.*'
```

MySuperWhisper auto-detects and preloads those venv-local CUDA libraries on startup. It also searches older Python-versioned site-packages directories inside the same venv, which helps when the venv survives a Python minor-version upgrade. This does not change the system-wide CUDA installation.

## Usage

### Starting the Application

```bash
# Using the virtual environment
./venv/bin/python -m mysuperwhisper

# Or with the legacy script
./venv/bin/python mysuperwhisper.py

# Or use the repo wrapper (works from any current directory)
/home/rafa/tools/MySuperWhisper/scripts/run-mysuperwhisper
```

### GNOME Wayland

On GNOME Wayland, `pynput`'s global keyboard listener is not reliable and its `uinput` backend may require root-level keyboard layout access. The recommended setup is:

```bash
# Start the main app in the user session
/home/rafa/tools/MySuperWhisper/scripts/run-mysuperwhisper --no-tray
```

Then create GNOME custom shortcuts that call the running instance:

```bash
/home/rafa/tools/MySuperWhisper/scripts/mysuperwhisper-toggle
/home/rafa/tools/MySuperWhisper/scripts/mysuperwhisper-history
```

This keeps audio capture, transcription, text injection, config, and logs in the normal user session, without running the full app as root.

Do not use `.../venv/bin/python -m mysuperwhisper ...` directly in GNOME shortcuts unless you also force the working directory to the repo. GNOME custom shortcuts usually launch from another directory, so the wrapper scripts above are the reliable option.

If your tray setup is working under GNOME Wayland, you can omit `--no-tray`. If the session bus or tray integration is unavailable, MySuperWhisper now logs the reason and keeps running headless instead of crashing.

### Recommended GNOME Wayland Setup

1. Start the app:

```bash
/home/rafa/tools/MySuperWhisper/scripts/run-mysuperwhisper
```

2. Add a GNOME custom shortcut for record start/stop:

```bash
/home/rafa/tools/MySuperWhisper/scripts/mysuperwhisper-toggle
```

3. Add a GNOME custom shortcut for history:

```bash
/home/rafa/tools/MySuperWhisper/scripts/mysuperwhisper-history
```

4. Keep `ydotool` installed for text injection.

This is the main supported Wayland workflow for this fork.

### Keyboard Shortcuts

**Default shortcuts on X11:**

| Shortcut | Action |
|----------|--------|
| **Double Left Ctrl** | Start/Stop recording |
| **Triple Left Ctrl** | Open transcription history |

Keyboard shortcuts are **fully configurable** via the system tray menu under "⌨️ Keyboard Shortcuts". Click "Configure..." to open the shortcut detection popup:

1. **Press your desired shortcut** exactly as you want to use it (e.g., double-tap Ctrl+A, triple Right Ctrl, single F1...)
2. The popup **shows in real-time** what is detected (key, combination, and tap count)
3. Click **OK** to validate

You can use **any key or combination**: modifier keys (Ctrl, Alt, Shift), function keys (F1-F12), regular keys (A-Z, 0-9), or combinations like Ctrl+A, Alt+Space, Shift+F1, etc.

On GNOME Wayland, use the command-based shortcuts shown above instead of the built-in `pynput` listener.

### System Tray

Right-click the tray icon to access:
- Enable/disable notifications
- Toggle clipboard paste for applications that need clipboard-based insertion
- Configure keyboard shortcuts
- View transcription history
- Test microphone with audio loopback
- Select AI model size
- Select language and transcription task
- Choose input/output audio devices
- Open configuration files

### Tray Icon Colors

| Color | Status |
|-------|--------|
| 🟡 Yellow | Loading model |
| 🟢 Green | Ready |
| 🔴 Red | Recording |
| 🟠 Orange | Transcribing |
| 🔵 Blue | Mic test mode |

## Voice Commands

MySuperWhisper recognizes voice commands in multiple languages:

### New Line Commands
| Language | Commands |
|----------|----------|
| English | "new line", "newline", "line break", "next line" |
| French | "retour à la ligne", "nouvelle ligne", "à la ligne" |
| Spanish | "nueva línea", "salto de línea", "línea siguiente" |

### Validation Commands (Press Enter)
| Language | Commands |
|----------|----------|
| English | "enter", "submit", "validate", "send", "confirm" |
| French | "valider", "entrée", "entrer" |
| Spanish | "enviar", "validar", "confirmar", "entrar" |

### Example

Say: *"Hello new line How are you enter"*

Result: Types "Hello", creates a new line, types "How are you", then presses Enter.

> **Note**: In standard applications, "new line" uses `Shift+Enter` (soft line break). In **terminal emulators**, it intelligently switches to `Ctrl+Shift+V` to paste the text with actual newlines, ensuring correct behavior.

### Paste behavior

The tray option **Use clipboard to paste** controls text insertion:

| Mode | Setting | How it works |
|------|---------|--------------|
| Direct typing (default) | `false` | Uses `ydotool` when available, then `wtype` on Wayland or `xdotool` on X11. Leaves the clipboard untouched. |
| Clipboard paste | `true` | Copies the text and sends `Ctrl+V`, or `Ctrl+Shift+V` for detected terminals. Useful for applications that need clipboard-based Unicode input. |

Direct typing is usually the best fit for GNOME Wayland. Turn on clipboard paste from the tray menu when an application does not accept injected text.

## Configuration

Configuration is stored in `~/.config/mysuperwhisper/config.json`:

```json
{
    "model_size": "medium",
    "language": "en",
    "task": "transcribe",
    "record_hotkey": "ctrl_l+a",
    "record_press_count": 2,
    "history_hotkey": "ctrl_l",
    "history_press_count": 3,
    "input_device": "Your Microphone",
    "output_device": "Your Speakers",
    "system_notifications_enabled": true,
    "sound_notifications_enabled": true,
    "use_clipboard_to_paste": false
}
```

This example configures:
- Double press of Left Ctrl + A for recording
- Triple press of Left Ctrl for history
- English language transcription

### Configuration Options

- **model_size**: Size of Whisper model (see Model Sizes table below)
- **language**: Language code for transcription (`"en"`, `"fr"`, `"es"`, etc.) or `null` for auto-detection
- **task**: Either `"transcribe"` (default) or `"translate"` (translates audio to English)
- **record_hotkey**: Key or combination for recording - any key (`"ctrl_l"`, `"f1"`, `"a"`) or combination (`"ctrl_l+a"`, `"alt+space"`)
- **record_press_count**: Number of presses for recording - `1` (single), `2` (double), or `3` (triple)
- **history_hotkey**: Key or combination for opening history popup
- **history_press_count**: Number of presses for history popup
- **input_device** / **output_device**: Audio device names (set via tray menu)
- **system_notifications_enabled**: Show desktop notifications
- **sound_notifications_enabled**: Play audio beeps
- **use_clipboard_to_paste**: Use the clipboard for insertion instead of direct typing

**Tip:** You can configure keyboard shortcuts easily through the system tray menu under "⌨️ Keyboard Shortcuts" — a detection popup lets you set shortcuts by simply pressing them, no manual editing needed.

When the process is launched with `sudo`, MySuperWhisper now prefers the invoking user's XDG directories if `SUDO_USER` is present. You can also override the storage roots explicitly with:

- `MYSUPERWHISPER_HOME`
- `MYSUPERWHISPER_CONFIG_HOME`
- `MYSUPERWHISPER_DATA_HOME`

### Model Sizes

| Model | VRAM | Speed | Accuracy |
|-------|------|-------|----------|
| tiny | ~1GB | Fastest | Basic |
| base | ~1GB | Fast | Good |
| small | ~2GB | Medium | Better |
| **medium** | ~2GB | Standard | **Recommended** |
| large-v3 | ~3.3GB | Slow | Best |

## File Locations

| File | Location |
|------|----------|
| Configuration | `~/.config/mysuperwhisper/config.json` |
| Logs | `~/.local/share/mysuperwhisper/logs/` |
| History | `~/.local/share/mysuperwhisper/history.json` |
| Runtime socket/lock | `$XDG_RUNTIME_DIR/mysuperwhisper/` or `/tmp/mysuperwhisper-UID/` |

## Project Structure

```
MySuperWhisper/
├── mysuperwhisper/          # Main package
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── main.py              # Application logic
│   ├── config.py            # Configuration management
│   ├── audio.py             # Audio capture
│   ├── transcription.py     # Whisper integration
│   ├── voice_commands.py    # Voice command processing
│   ├── paste.py             # Text input simulation
│   ├── notifications.py     # Notifications
│   ├── keyboard.py          # Hotkey handling
│   ├── history.py           # History management
│   └── tray.py              # System tray
├── scripts/                 # Wrapper launchers for desktop/shortcut use
├── install.sh               # Installation script
├── requirements.txt         # Python dependencies
├── LICENSE                  # MIT License
├── CONTRIBUTING.md          # Contribution guidelines
└── README.md                # This file
```

## Troubleshooting

### No audio input
- Check microphone permissions
- Verify correct input device in tray menu
- Use "Mic Test" to verify audio is being captured

### Slow transcription
- Ensure CUDA is available for GPU acceleration
- Try a smaller model (tiny, base, small)
- Check if running in CPU mode (indicated in tray tooltip with [CPU])

### GPU issues after driver update
- If you recently updated your NVIDIA drivers, the app might fallback to CPU mode or fail to load the model.
- **Solution:** Restart your computer to ensure the new drivers are correctly loaded.

### Text not typed in some applications
- Some applications may not accept simulated keyboard input
- On Linux, `ydotool` is the preferred text injection backend and works better on Wayland than clipboard-driven paste
- Turn on **Use clipboard to paste** in the tray menu for applications that need clipboard-based insertion
- If direct typing fails, the app reports the failure and leaves the clipboard unchanged

### CUDA loads but transcription fails on missing `libcublas.so.12`
- Install the venv-local CUDA runtime:
  `./venv/bin/pip install 'nvidia-cublas-cu12' 'nvidia-cudnn-cu12==9.*'`
- Restart the app
- This fork auto-loads those libraries from the venv when present

### New line doesn't work in terminal
- This should be handled automatically now (auto-switch to Ctrl+Shift+V)
- If not, try pasting manually using Ctrl+Shift+V

### GNOME Wayland hotkeys do nothing
- Start the main app once with `/home/rafa/tools/MySuperWhisper/scripts/run-mysuperwhisper --no-tray`
- Add GNOME custom shortcuts for `/home/rafa/tools/MySuperWhisper/scripts/mysuperwhisper-toggle` and `/home/rafa/tools/MySuperWhisper/scripts/mysuperwhisper-history`
- Only use `--enable-pynput-hotkeys` on Wayland if you intentionally want to experiment with the old listener behavior

## Dependencies

MySuperWhisper uses these excellent open-source projects:

| Package | Purpose | License |
|---------|---------|---------|
| [faster-whisper](https://github.com/guillaumekln/faster-whisper) | Whisper implementation | MIT |
| [pynput](https://github.com/moses-palmer/pynput) | Keyboard monitoring | LGPL-3.0 |
| [pystray](https://github.com/moses-palmer/pystray) | System tray | LGPL-3.0 |
| [sounddevice](https://python-sounddevice.readthedocs.io/) | Audio capture | MIT |
| [numpy](https://numpy.org/) | Numerical processing | BSD |
| [Pillow](https://pillow.readthedocs.io/) | Image processing | HPND |
| [pyperclip](https://github.com/asweigart/pyperclip) | Clipboard access | BSD |

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- OpenAI for the Whisper model
- The faster-whisper team for the optimized implementation
- All contributors and users of this project

---

<p align="center">
  Made with ❤️ for the Linux community
</p>
