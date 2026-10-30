# SwapTrack

SwapTrack is a small desktop app that replaces a video's original audio with an audio file you choose.

- Simple Tkinter GUI with no heavy GUI dependencies
- Video stream is copied without re-encoding
- Match the video's length, loop the audio, or stop at the shorter input
- Volume control from 0% to 200%
- Progress reporting and cancellation
- Windows, macOS, and Linux support
- FFmpeg is supplied automatically by `imageio-ffmpeg`

## Requirements

- Python 3.9+
- Tkinter
- `pip`

On Linux, if Tkinter is missing:

```bash
sudo apt install python3-tk
```

## Install

```bash
git clone https://github.com/D3F4ULT64/Swaptrack.git
cd Swaptrack
python -m pip install -r requirements.txt
```

## Run

```bash
python run.py
```

or:

```bash
python -m swaptrack
```

Choose a video, choose the replacement audio, choose an output file, select a length mode, adjust the volume, and click **Replace audio**.

### Length modes

| Mode | Behavior |
| --- | --- |
| Match video length | Trims longer audio and pads shorter audio with silence. |
| Loop audio | Repeats the replacement audio until the video ends. |
| Stop at whichever is shorter | Ends when either the video or audio ends. |

### Supported containers

The GUI offers MP4, MOV, MKV, WebM, and AVI. For best results, keep the output container compatible with the video's existing video codec because SwapTrack intentionally copies the video stream instead of re-encoding it. WebM uses Opus audio; other containers use AAC audio.

## Library API

```python
from swaptrack.core import LengthMode, swap_audio

swap_audio(
    "clip.mp4",
    "song.mp3",
    "clip_swapped.mp4",
    mode=LengthMode.LOOP_AUDIO,
    volume=0.8,
)
```

`swap_audio()` raises `SwapError` for invalid inputs or FFmpeg failures and `Cancelled` when a supplied cancellation event is triggered.

## Project layout

```text
Swaptrack/
├── run.py
├── requirements.txt
├── LICENSE
├── README.md
└── swaptrack/
    ├── __init__.py
    ├── __main__.py
    ├── core.py
    └── gui.py
```

## Development

Run the unit tests with:

```bash
python -m unittest discover -s tests -v
```

The repository also runs the test suite automatically with GitHub Actions.

## License

MIT
