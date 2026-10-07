import unittest
from pathlib import Path

from shared.api.segments import build_extract_command, concat_entry


class BuildExtractCommandTest(unittest.TestCase):
    def test_copy_mode_seeks_input_and_uses_duration(self):
        cmd = build_extract_command(Path("in.mp4"), 1.25, 3.5, Path("out.mp4"), reencode=False)
        self.assertLess(cmd.index("-ss"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-ss") + 1], "1.250")
        self.assertEqual(cmd[cmd.index("-t") + 1], "2.250")
        self.assertNotIn("-to", cmd)
        self.assertIn("copy", cmd)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_reencode_mode_uses_libx264_aac(self):
        cmd = build_extract_command(Path("in.mp4"), 0, 1, Path("out.mp4"), reencode=True)
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "libx264")
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "aac")
        self.assertNotIn("copy", cmd)

    def test_pad_extends_duration_with_silence_and_frozen_frame(self):
        cmd = build_extract_command(Path("in.mp4"), 1.0, 2.0, Path("out.mp4"), reencode=True, pad=0.05)
        self.assertEqual(cmd[cmd.index("-t") + 1], "1.050")
        self.assertEqual(cmd[cmd.index("-af") + 1], "apad=pad_dur=0.050")
        self.assertEqual(cmd[cmd.index("-vf") + 1], "tpad=stop_mode=clone:stop_duration=0.050")

    def test_pad_requires_reencode(self):
        with self.assertRaises(ValueError):
            build_extract_command(Path("in.mp4"), 0, 1, Path("out.mp4"), reencode=False, pad=0.05)


class ConcatEntryTest(unittest.TestCase):
    def test_uses_forward_slashes_and_escapes_quotes(self):
        entry = concat_entry(Path("dir with space") / "it's 클로드.mp4")
        self.assertTrue(entry.startswith("file '"))
        self.assertNotIn("\\", entry.replace("'\\''", ""))
        self.assertIn("it'\\''s 클로드.mp4", entry)


if __name__ == "__main__":
    unittest.main()
