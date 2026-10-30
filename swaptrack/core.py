"""Core logic for replacing a video's audio track with FFmpeg."""

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
    MATCH_VIDEO = "match_video"
    LOOP_AUDIO = "loop_audio"
    SHORTEST = "shortest"


_PROGRESS_KEYS = {
    "frame", "fps", "stream_0_0_q", "bitrate", "total_size", "out_time_us",
    "out_time_ms", "out_time", "dup_frames", "drop_frames", "speed", "progress",
}


def find_ffmpeg() -> str:
    """Locate bundled FFmpeg first, then fall back to the system PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    found = shutil.which("ffmpeg")
    if found:
        return found
    raise SwapError(
        "FFmpeg was not found. Install dependencies with "
        "`python -m pip install -r requirements.txt`, or install FFmpeg and add it to PATH."
    )


def _popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def probe_duration(ffmpeg: str, path: Path) -> Optional[float]:
    """Return media duration in seconds, or None if it cannot be determined."""
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
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def build_command(
    ffmpeg: str,
    video: Path,
    audio: Path,
    output: Path,
    mode: LengthMode = LengthMode.MATCH_VIDEO,
    volume: float = 1.0,
    video_duration: Optional[float] = None,
) -> list[str]:
    """Build the FFmpeg command without executing it."""
    mode = LengthMode(mode)
    if not 0.0 <= volume <= 2.0:
        raise SwapError("Volume must be between 0% and 200%.")

    ext = output.suffix.lower()
    audio_codec = ["-c:a", "libopus", "-b:a", "160k"] if ext == ".webm" else ["-c:a", "aac", "-b:a", "192k"]

    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats",
        "-progress", "pipe:1", "-y", "-i", str(video),
    ]
    if mode == LengthMode.LOOP_AUDIO:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]

    filters: list[str] = []
    if abs(volume - 1.0) > 1e-3:
        filters.append(f"volume={volume:.3f}")

    if mode == LengthMode.MATCH_VIDEO:
        if video_duration is None:
            raise SwapError("Could not determine the video's duration.")
        filters.append("apad")
        cmd += ["-t", f"{video_duration:.3f}"]
    elif mode in (LengthMode.LOOP_AUDIO, LengthMode.SHORTEST):
        cmd += ["-shortest"]

    if filters:
        cmd += ["-af", ",".join(filters)]

    cmd += audio_codec
    if ext in {".mp4", ".m4v", ".mov"}:
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
    """Replace the video's audio and write the result to ``output``."""
    video, audio, output = Path(video), Path(audio), Path(output)

    if not video.is_file():
        raise SwapError(f"Video file not found:\n{video}")
    if not audio.is_file():
        raise SwapError(f"Audio file not found:\n{audio}")
    if video.resolve() == output.resolve() or audio.resolve() == output.resolve():
        raise SwapError("The output file must be different from the input files.")
    if not output.parent.exists():
        raise SwapError(f"Output folder does not exist:\n{output.parent}")
    if not output.suffix:
        raise SwapError("The output file needs a filename extension, such as .mp4.")
    if not 0.0 <= volume <= 2.0:
        raise SwapError("Volume must be between 0% and 200%.")

    try:
        mode = LengthMode(mode)
    except ValueError as exc:
        raise SwapError(f"Unknown length mode: {mode}") from exc

    ffmpeg = find_ffmpeg()
    duration = probe_duration(ffmpeg, video)
    cmd = build_command(ffmpeg, video, audio, output, mode, volume, duration)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_popen_kwargs(),
    )

    log_tail: deque[str] = deque(maxlen=30)
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
                        seconds = int(value) / 1_000_000
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

    if not output.is_file() or output.stat().st_size == 0:
        raise SwapError("FFmpeg finished without creating a valid output file.")

    if on_progress:
        on_progress(1.0)
    return output
