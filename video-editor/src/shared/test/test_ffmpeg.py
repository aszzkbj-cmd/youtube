import subprocess
import unittest
from pathlib import Path
from unittest import mock

from shared.api import CommandError, ToolNotFoundError, has_audio, probe_duration, require_tools, run


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class RequireToolsTest(unittest.TestCase):
    def test_raises_with_missing_tools_and_install_guide(self):
        with mock.patch("shared.api.ffmpeg.shutil.which", return_value=None):
            with self.assertRaises(ToolNotFoundError) as ctx:
                require_tools()
        self.assertEqual(ctx.exception.missing, ["ffmpeg", "ffprobe"])
        self.assertIn("winget install Gyan.FFmpeg", str(ctx.exception))

    def test_passes_when_all_tools_exist(self):
        with mock.patch("shared.api.ffmpeg.shutil.which", return_value="/bin/x"):
            require_tools()


class RunTest(unittest.TestCase):
    def test_failure_raises_with_command_and_stderr(self):
        with mock.patch("shared.api.ffmpeg.subprocess.run", return_value=completed(stderr="boom", returncode=1)):
            with self.assertRaises(CommandError) as ctx:
                run(["ffmpeg", "-i", "a b.mp4"])
        message = str(ctx.exception)
        self.assertIn('ffmpeg -i "a b.mp4"', message)
        self.assertIn("boom", message)
        self.assertEqual(ctx.exception.returncode, 1)

    def test_decodes_output_as_utf8(self):
        with mock.patch("shared.api.ffmpeg.subprocess.run", return_value=completed("ok")) as m:
            run(["ffmpeg"])
        self.assertEqual(m.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(m.call_args.kwargs["errors"], "replace")


class ProbeTest(unittest.TestCase):
    def test_probe_duration_parses_float(self):
        with mock.patch("shared.api.ffmpeg.subprocess.run", return_value=completed("12.5\n")):
            self.assertEqual(probe_duration(Path("x.mp4")), 12.5)

    def test_probe_duration_invalid_output_raises(self):
        with mock.patch("shared.api.ffmpeg.subprocess.run", return_value=completed("N/A\n")):
            with self.assertRaises(CommandError):
                probe_duration(Path("x.mp4"))

    def test_has_audio(self):
        with mock.patch("shared.api.ffmpeg.subprocess.run", return_value=completed("1\n")):
            self.assertTrue(has_audio(Path("x.mp4")))
        with mock.patch("shared.api.ffmpeg.subprocess.run", return_value=completed("")):
            self.assertFalse(has_audio(Path("x.mp4")))


if __name__ == "__main__":
    unittest.main()
