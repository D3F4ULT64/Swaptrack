# SwapTrack

A small desktop app that **removes a video's original audio and replaces it with any audio file you choose.**

- Simple GUI (built with Tkinter, no heavy dependencies)
- Video is **not re-encoded**, so it's fast and there's no quality loss
- Choose what happens when lengths differ: match the video, loop the audio, or stop at the shorter one
- Volume control, progress bar, and cancel button
- Works on Windows, macOS, and Linux

## Install

Requires Python 3.9+ (with Tkinter, which ships with the standard Python installers).

```bash
git clone https://github.com/<your-username>/swaptrack.git
cd swaptrack
pip install -r requirements.txt
```

FFmpeg is bundled through [`imageio-ffmpeg`](https://pypi.org/project/imageio-ffmpeg/), so you don't need to install it separately. If you already have FFmpeg on your PATH, it's used as a fallback.

> **Linux:** if Tkinter is missing, install it with `sudo apt install python3-tk`.

## Run

```bash
python run.py
# or
python -m swaptrack
```

1. **Video**: pick any video file
2. **New audio**: pick the audio that should replace it (mp3, wav, m4a, flac, ogg, ...)
3. **Save as**: choose the output file (auto-filled as `<name>_swapped.<ext>`)
4. Pick a length mode and volume, then click **Replace audio**

### Length modes

| Mode | Behavior |
| --- | --- |
| Match video length | Audio is trimmed if longer, padded with silence if shorter (default) |
| Loop audio | Audio repeats until the video ends |
| Stop at shorter | Output ends when the shorter of the two ends |

## Use it as a library

```python
from swaptrack.core import swap_audio, LengthMode

swap_audio("clip.mp4", "song.mp3", "clip_new.mp4", mode=LengthMode.LOOP_AUDIO, volume=0.8)
```

## Project layout

```
swaptrack/
├── run.py              # launcher
├── requirements.txt
└── swaptrack/
    ├── core.py         # FFmpeg logic (no GUI code)
    └── gui.py          # Tkinter interface
```

## Notes

- The output container should suit the video codec (e.g. H.264 into `.mp4`/`.mkv`). Keeping the same extension as the input is the safest choice.
- `.webm` outputs use Opus audio; everything else uses AAC.

## License

MIT
