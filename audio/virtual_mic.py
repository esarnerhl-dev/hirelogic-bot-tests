"""
audio/virtual_mic.py
Manages a PulseAudio virtual sink/source to inject known audio into meetings.

On Linux CI (and in Docker), PulseAudio creates a virtual "null sink" that
acts as both a speaker and mic. Playwright is launched with --use-fake-ui-for-media-stream
which picks up this virtual device.

macOS alternative: BlackHole audio driver (see README).
"""

import logging
import os
import subprocess
import time
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

SINK_NAME = "hirelogic_test"
SINK_DESCRIPTION = "HireLogic Test Virtual Mic"


class VirtualMic:
    """
    Manages a PulseAudio null sink for audio injection.

    The sink acts as a loopback: audio played to the sink becomes
    available as a microphone source (sink.monitor).

    Usage:
        mic = VirtualMic()
        mic.start()
        # ... play audio files into it ...
        mic.stop()

    Or as a context manager:
        with VirtualMic() as mic:
            mic.play("path/to/audio.wav")
    """

    def __init__(self, sink_name: str = SINK_NAME):
        self.sink_name = sink_name
        self.source_name = f"{sink_name}.monitor"
        self._module_id: Optional[str] = None
        self._play_proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        """Load the PulseAudio null sink module."""
        if self._is_running():
            logger.debug(f"[VirtualMic] Sink '{self.sink_name}' already exists, reusing")
            return

        result = subprocess.run(
            [
                "pactl", "load-module", "module-null-sink",
                f"sink_name={self.sink_name}",
                f"sink_properties=device.description={SINK_DESCRIPTION}",
            ],
            capture_output=True, text=True, timeout=10,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"[VirtualMic] Failed to load null sink: {result.stderr.strip()}\n"
                "Ensure PulseAudio is running: pulseaudio --start"
            )

        self._module_id = result.stdout.strip()
        logger.info(f"[VirtualMic] Loaded null sink module {self._module_id} → {self.sink_name}")
        time.sleep(0.5)  # Allow PulseAudio to register the device

    def stop(self) -> None:
        """Unload the null sink module."""
        self._stop_playback()

        if self._module_id:
            try:
                subprocess.run(
                    ["pactl", "unload-module", self._module_id],
                    capture_output=True, timeout=5,
                )
                logger.info(f"[VirtualMic] Unloaded module {self._module_id}")
            except Exception as e:
                logger.warning(f"[VirtualMic] Could not unload module: {e}")
            finally:
                self._module_id = None

    def play(self, wav_path: str, loop: bool = False) -> None:
        """
        Play a WAV file into the virtual sink asynchronously.
        Stops any currently playing audio first.
        """
        self._stop_playback()

        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Audio fixture not found: {wav_path}")

        cmd = ["paplay", f"--device={self.sink_name}", wav_path]
        if loop:
            # Loop via sox: play → loop
            cmd = ["sox", "-q", wav_path, "-t", "pulseaudio", self.sink_name, "repeat", "9999"]

        logger.info(f"[VirtualMic] Playing {os.path.basename(wav_path)} → {self.sink_name}")
        self._play_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def play_sync(self, wav_path: str) -> None:
        """Play a WAV file and block until it finishes."""
        self.play(wav_path)
        if self._play_proc:
            self._play_proc.wait()
            self._play_proc = None

    def play_silence(self, duration_seconds: int = 10) -> None:
        """Generate and play silence (useful for edge case testing)."""
        import tempfile
        import wave
        import struct

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        sample_rate = 16000
        n_samples = sample_rate * duration_seconds
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))

        self.play_sync(tmp_path)
        os.unlink(tmp_path)

    def stop_playback(self) -> None:
        """Stop currently playing audio without tearing down the sink."""
        self._stop_playback()

    def _stop_playback(self) -> None:
        if self._play_proc and self._play_proc.poll() is None:
            self._play_proc.terminate()
            self._play_proc.wait(timeout=3)
        self._play_proc = None

    def _is_running(self) -> bool:
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, timeout=5,
            )
            return self.sink_name in result.stdout
        except Exception:
            return False

    def get_source_name(self) -> str:
        """Return the monitor source name for use in Playwright launch args."""
        return self.source_name

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


@contextmanager
def virtual_mic(sink_name: str = SINK_NAME):
    """Convenience context manager."""
    mic = VirtualMic(sink_name)
    mic.start()
    try:
        yield mic
    finally:
        mic.stop()
