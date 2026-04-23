"""
Audio capture and processing for MySuperWhisper.
Handles microphone input, recording, and audio device management.

Uses PulseAudio/PipeWire for device enumeration (like Slack/Meet)
and sounddevice with the 'pulse' backend for audio capture.
"""

import os
import queue
import subprocess
import re
import time
import threading
import numpy as np
import sounddevice as sd
from .config import log, config

# Audio settings
SAMPLE_RATE = 48000  # Best hardware compatibility
WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz

# Global state
audio_buffer = []
is_recording = False
_stream = None
_test_queue = queue.Queue()
_is_testing_mic = False

# Cache for PulseAudio devices
_pulse_sources_cache = None
_pulse_sinks_cache = None


def _get_pulse_device_index():
    """Get the sounddevice index for the 'pulse' device."""
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev['name'].lower() == 'pulse':
                return i
        # Fallback to pipewire or default
        for i, dev in enumerate(devices):
            if 'pipewire' in dev['name'].lower():
                return i
    except Exception as e:
        log(f"Error finding pulse device: {e}", "warning")
    return None


def get_pulse_sources():
    """
    Get list of PulseAudio input sources (microphones).
    Returns the same devices that Slack/Meet show.

    Returns:
        list: List of dicts with 'name', 'description', 'is_default'
    """
    global _pulse_sources_cache
    sources = []

    try:
        # Get list of sources
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=5
        )

        # Get default source
        default_result = subprocess.run(
            ["pactl", "get-default-source"],
            capture_output=True, text=True, timeout=5
        )
        default_source = default_result.stdout.strip()

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[1]
                # Skip monitor sources (they capture output, not input)
                if '.monitor' in name:
                    continue

                # Get friendly description
                desc = _get_pulse_device_description(name, "source")
                if desc:
                    sources.append({
                        'name': name,
                        'description': desc,
                        'is_default': name == default_source
                    })

        _pulse_sources_cache = sources
    except Exception as e:
        log(f"Error getting PulseAudio sources: {e}", "warning")
        if _pulse_sources_cache:
            return _pulse_sources_cache

    return sources


def get_pulse_sinks():
    """
    Get list of PulseAudio output sinks (speakers).
    Returns the same devices that Slack/Meet show.

    Returns:
        list: List of dicts with 'name', 'description', 'is_default'
    """
    global _pulse_sinks_cache
    sinks = []

    try:
        # Get list of sinks
        result = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=5
        )

        # Get default sink
        default_result = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, text=True, timeout=5
        )
        default_sink = default_result.stdout.strip()

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[1]

                # Get friendly description
                desc = _get_pulse_device_description(name, "sink")
                if desc:
                    sinks.append({
                        'name': name,
                        'description': desc,
                        'is_default': name == default_sink
                    })

        _pulse_sinks_cache = sinks
    except Exception as e:
        log(f"Error getting PulseAudio sinks: {e}", "warning")
        if _pulse_sinks_cache:
            return _pulse_sinks_cache

    return sinks


def _get_pulse_device_description(device_name, device_type):
    """Get the friendly description for a PulseAudio device."""
    try:
        # Use LANG=C to get English output regardless of system locale
        env = dict(os.environ)
        env['LANG'] = 'C'

        cmd = ["pactl", "list", f"{device_type}s"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=env)

        # Parse output to find the device and its description
        current_name = None
        for line in result.stdout.split('\n'):
            stripped = line.strip()
            # Match "Name: xxx"
            if stripped.startswith('Name:'):
                current_name = stripped.split(':', 1)[1].strip()
            # Match "Description: xxx"
            elif stripped.startswith('Description:'):
                if current_name == device_name:
                    return stripped.split(':', 1)[1].strip()

    except Exception as e:
        log(f"Error getting device description: {e}", "debug")

    # Fallback: extract a readable name from the technical name
    if 'Razer' in device_name:
        return "Razer USB Sound Card"

    return device_name.split('.')[-1].replace('_', ' ')


def set_default_source(source_name):
    """
    Set the input source (microphone).
    Updates configuration and restarts audio stream.
    Does NOT change system default (pactl), only app-specific selection.
    """
    if config.input_device == source_name:
        return True

    log(f"Setting input device to: {source_name}")
    config.input_device = source_name
    config.save()
    
    restart_stream()
    restart_mic_test()
    return True


def set_default_sink(sink_name):
    """
    Set the output sink (speaker).
    Updates configuration.
    Does NOT change system default, only app-specific selection.
    """
    if config.output_device == sink_name:
        return True

    log(f"Setting output device to: {sink_name}")
    config.output_device = sink_name
    config.save()
    restart_mic_test()
    return True


def get_devices():
    """
    Get list of audio devices (legacy compatibility).
    Now returns PulseAudio devices in a compatible format.

    Returns:
        list: List of device dictionaries
    """
    # For backward compatibility with code expecting sounddevice format
    return sd.query_devices()


def _audio_callback(indata, frames, time_info, status):
    """
    Callback called by sounddevice for each audio block.

    Note: This is time-critical code. No slow or blocking calls.
    """
    if is_recording:
        audio_buffer.append(indata.copy())

    if _is_testing_mic:
        try:
            _test_queue.put(indata.copy(), block=False)
        except queue.Full:
            pass


def start_stream(device_index=None):
    """
    Start the audio input stream using PulseAudio.
    The actual microphone is controlled by pactl set-default-source.
    """
    global _stream

    if _stream:
        stop_stream()

    try:
        # Always use pulse device - actual mic is selected via pactl
        pulse_idx = _get_pulse_device_index()
        device = pulse_idx if pulse_idx is not None else None

        log(f"Opening audio stream via PulseAudio...")

        # Set PulseAudio source from config if specified
        if config.input_device:
            os.environ["PULSE_SOURCE"] = config.input_device
            log(f"Using input device: {config.input_device}")
        elif "PULSE_SOURCE" in os.environ:
            del os.environ["PULSE_SOURCE"]

        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            device=device,
            channels=1,
            callback=_audio_callback
        )
        _stream.start()
        log("Audio stream started")

    except Exception as e:
        log(f"Cannot open PulseAudio device: {e}", "warning")
        log("Trying default device...", "warning")

        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            callback=_audio_callback
        )
        _stream.start()


def ensure_stream():
    """Ensure the audio input stream is open."""
    if _stream is None:
        start_stream()


def stop_stream():
    """Stop the audio input stream."""
    global _stream

    if _stream:
        _stream.stop()
        _stream.close()
        _stream = None
        log("Audio stream stopped")


def restart_stream():
    """Restart the audio stream."""
    if _stream:
        stop_stream()
        start_stream()


def release_stream_if_idle():
    """Release the microphone when not recording and not testing."""
    if not is_recording and not _is_testing_mic:
        stop_stream()


def start_recording():
    """Start recording audio."""
    global is_recording, audio_buffer

    ensure_stream()
    log("Recording started... (Double Ctrl to stop)")
    audio_buffer = []  # Reset buffer
    is_recording = True


def stop_recording():
    """
    Stop recording and return captured audio.

    Returns:
        numpy.ndarray or None: Captured audio data, or None if empty
    """
    global is_recording

    log("Recording stopped.")
    is_recording = False
    release_stream_if_idle()

    if not audio_buffer:
        log("No audio recorded.", "warning")
        return None

    try:
        # Concatenate all audio blocks
        full_audio = np.concatenate(audio_buffer, axis=0)
        return full_audio
    except ValueError:
        log("Error concatenating audio", "error")
        return None


def prepare_for_whisper(audio_data):
    """
    Prepare audio data for Whisper transcription.

    Whisper expects 16kHz mono audio. We capture at 48kHz for better
    hardware compatibility, so we downsample here.

    Args:
        audio_data: Raw audio at 48kHz

    Returns:
        numpy.ndarray: Audio at 16kHz suitable for Whisper
    """
    # Downsample from 48kHz to 16kHz (keep every 3rd sample)
    # 48000 / 3 = 16000
    return audio_data[::3].flatten()


def is_currently_recording():
    """Check if currently recording."""
    return is_recording


# --- Microphone Test Mode ---

_test_callback = None
_test_thread = None

def start_mic_test(callback=None):
    """Start microphone test mode with loopback."""
    global _is_testing_mic, _test_callback, _test_thread
    
    if _is_testing_mic:
        return
        
    _is_testing_mic = True
    ensure_stream()
    if callback:
        _test_callback = callback
    
    # Start worker thread
    if _test_callback:
        _test_thread = threading.Thread(
            target=mic_test_worker,
            args=(_test_callback,),
            daemon=True
        )
        _test_thread.start()


def stop_mic_test():
    """Stop microphone test mode."""
    global _is_testing_mic
    _is_testing_mic = False
    release_stream_if_idle()


def restart_mic_test():
    """Restart mic test if active (e.g. after device change)."""
    global _is_testing_mic
    
    if not _is_testing_mic:
        return

    log("Restarting mic test for new device...")
    
    # 1. Stop current test
    _is_testing_mic = False
    
    # 2. Wait for thread to finish (max 0.6s as configured in worker)
    if _test_thread and _test_thread.is_alive():
        _test_thread.join(timeout=1.0)
        
    # 3. Start new test
    start_mic_test(_test_callback)


def is_testing_mic():
    """Check if mic test mode is active."""
    return _is_testing_mic


def mic_test_worker(update_ui_callback):
    """
    Worker thread for microphone test with audio loopback.

    Args:
        update_ui_callback: Function to call with audio level (0.0-1.0)
    """
    last_ui_update = 0

    try:
        # Use pulse device for output too
        pulse_idx = _get_pulse_device_index()

        # Set PulseAudio sink from config if specified
        if config.output_device:
            os.environ["PULSE_SINK"] = config.output_device
            log(f"Using output device: {config.output_device}")
        elif "PULSE_SINK" in os.environ:
            del os.environ["PULSE_SINK"]

        with sd.OutputStream(
            samplerate=SAMPLE_RATE,
            device=pulse_idx,
            channels=2,
            blocksize=0
        ) as out:
            while _is_testing_mic:
                try:
                    data = _test_queue.get(timeout=0.5)
                except queue.Empty:
                    if time.time() - last_ui_update > 0.1:
                        update_ui_callback(0.0)
                        last_ui_update = time.time()
                    continue

                # Update UI with level
                if time.time() - last_ui_update > 0.1:
                    rms = np.sqrt(np.mean(data**2))
                    level = min(rms * 10, 1.0)
                    update_ui_callback(level)
                    last_ui_update = time.time()

                # Output audio (mono to stereo)
                stereo_data = np.column_stack((data, data))
                out.write(stereo_data)

    except Exception as e:
        log(f"Mic test loopback error: {e}", "error")
