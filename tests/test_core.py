import unittest
from pathlib import Path

from swaptrack.core import LengthMode, SwapError, build_command


class BuildCommandTests(unittest.TestCase):
    def setUp(self):
        self.video = Path("video.mp4")
        self.audio = Path("audio.mp3")
        self.output = Path("out.mp4")

    def test_match_video_pads_and_caps(self):
        cmd = build_command("ffmpeg", self.video, self.audio, self.output, LengthMode.MATCH_VIDEO, 1.0, 12.5)
        self.assertIn("apad", cmd)
        self.assertIn("-t", cmd)
        self.assertIn("12.500", cmd)
        self.assertNotIn("-shortest", cmd)

    def test_loop_audio_loops_and_uses_shortest(self):
        cmd = build_command("ffmpeg", self.video, self.audio, self.output, LengthMode.LOOP_AUDIO, 1.0, 12.5)
        self.assertIn("-stream_loop", cmd)
        self.assertIn("-1", cmd)
        self.assertIn("-shortest", cmd)

    def test_shortest_does_not_loop(self):
        cmd = build_command("ffmpeg", self.video, self.audio, self.output, LengthMode.SHORTEST, 1.0, 12.5)
        self.assertNotIn("-stream_loop", cmd)
        self.assertIn("-shortest", cmd)

    def test_volume_filter(self):
        cmd = build_command("ffmpeg", self.video, self.audio, self.output, LengthMode.SHORTEST, 0.75, 12.5)
        self.assertIn("volume=0.750", cmd)

    def test_invalid_volume_is_rejected(self):
        with self.assertRaises(SwapError):
            build_command("ffmpeg", self.video, self.audio, self.output, LengthMode.SHORTEST, 2.1, 12.5)

    def test_match_requires_duration(self):
        with self.assertRaises(SwapError):
            build_command("ffmpeg", self.video, self.audio, self.output, LengthMode.MATCH_VIDEO, 1.0, None)


if __name__ == "__main__":
    unittest.main()
