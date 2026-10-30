"""Core logic: builds and runs the FFmpeg command that swaps a video's audio.

The video stream is copied untouched (no re-encoding, so it's fast and
lossless). Only the new audio is encoded.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


class SwapError(Exception):
    """Raised when FFmpeg fails or inputs are invalid."""


class Cancelled(Exception):
    """Raised when the user cancels a running job."""


class LengthMode(str, Enum):
    MATCH_VIDEO = "match_video"  # trim audio / pad with silence to video length
    LOOP_AUDIO = "loop_audio"    # loop audio until the video ends
    SHORTEST = "shortest"        # end at whichever is shorter


_PROGRESS_KEYS = {
    "frame", "fps", "stream_0_0_q", "bitrate", "total_size", "out_time_us",
    "out_time_ms", "out_time", "dup_frames", "drop_frames", "speed", "progress",
}


def find_ffmpeg() -> str:
    """Locate FFmpeg: bundled binary (imageio-ffmpeg) first, then system PATH."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise SwapError(
        "FFmpeg was not found. Run `pip install -r requirements.txt` "
        "or install FFmpeg and add it to your PATH."
    )


def _popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def probe_duration(ffmpeg: str, path: Path) -> Optional[float]:
    """Return media duration in seconds, or None if it can't be determined."""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_popen_kwargs(),
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not match:
        return None
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def build_command(
    ffmpeg: str,
    video: Path,
    audio: Path,
    output: Path,
    mode: LengthMode = LengthMode.MATCH_VIDEO,
    volume: float = 1.0,
    video_duration: Optional[float] = None,
) -> list[str]:
    ext = output.suffix.lower()
    audio_codec = ["-c:a", "libopus", "-b:a", "160k"] if ext == ".webm" else ["-c:a", "aac", "-b:a", "192k"]

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-y"]
    cmd += ["-i", str(video)]
    if mode == LengthMode.LOOP_AUDIO:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(audio)]

    # Take the video from input 0 and audio from input 1 -> original audio is dropped.
    cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]

    filters = []
    if abs(volume - 1.0) > 1e-3:
        filters.append(f"volume={volume:.3f}")
    # apad makes the audio endless, so it's only safe with an explicit -t cap below.
    pad_and_cap = mode == LengthMode.MATCH_VIDEO and video_duration is not None
    if pad_and_cap:
        filters.append("apad")  # silence-pad if audio is shorter than the video
    if filters:
        cmd += ["-af", ",".join(filters)]

    cmd += audio_codec
    if pad_and_cap:
        cmd += ["-t", f"{video_duration:.3f}"]
    else:
        cmd += ["-shortest"]
    if ext in (".mp4", ".m4v", ".mov"):
        cmd += ["-movflags", "+faststart"]

    cmd += [str(output)]
    return cmd


def swap_audio(
    video: str | Path,
    audio: str | Path,
    output: str | Path,
    mode: LengthMode = LengthMode.MATCH_VIDEO,
    volume: float = 1.0,
    on_progress: Optional[Callable[[float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Replace the audio of `video` with `audio` and write the result to `output`.

    on_progress receives a float between 0.0 and 1.0.
    Raises SwapError on failure and Cancelled if cancel_event is set.
    """
    video, audio, output = Path(video), Path(audio), Path(output)

    if not video.is_file():
        raise SwapError(f"Video file not found:\n{video}")
    if not audio.is_file():
        raise SwapError(f"Audio file not found:\n{audio}")
    if output.resolve() in (video.resolve(), audio.resolve()):
        raise SwapError("The output file must be different from the input files.")
    if not output.parent.exists():
        raise SwapError(f"Output folder does not exist:\n{output.parent}")

    ffmpeg = find_ffmpeg()
    duration = probe_duration(ffmpeg, video)
    cmd = build_command(ffmpeg, video, audio, output, LengthMode(mode), volume, duration)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_popen_kwargs(),
    )

    log_tail: deque[str] = deque(maxlen=20)
    cancelled = False
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                proc.terminate()
                break
            line = raw.strip()
            if not line:
                continue
            key, _, value = line.partition("=")
            if key in _PROGRESS_KEYS:
                if key in ("out_time_us", "out_time_ms") and duration and on_progress:
                    try:
                        seconds = int(value) / 1_000_000  # both keys are in microseconds
                    except ValueError:
                        continue
                    on_progress(max(0.0, min(seconds / duration, 0.99)))
            else:
                log_tail.append(line)
    finally:
        code = proc.wait()

    if cancelled or (cancel_event is not None and cancel_event.is_set()):
        output.unlink(missing_ok=True)
        raise Cancelled()
    if code != 0:
        output.unlink(missing_ok=True)
        details = "\n".join(log_tail) or f"FFmpeg exited with code {code}."
        raise SwapError(details)

    if on_progress:
        on_progress(1.0)
    return output
