import unittest
from unittest import mock

from shared.api import detect_silences
from shared.api.silence import parse_silences


class ParseSilencesTest(unittest.TestCase):
    def test_parses_pairs_and_open_end(self):
        log = (
            "[silencedetect @ 0x1] silence_start: 1.5\n"
            "[silencedetect @ 0x1] silence_end: 3.25 | silence_duration: 1.75\n"
            "[silencedetect @ 0x1] silence_start: 8\n"
        )
        self.assertEqual(parse_silences(log, 10.0), [(1.5, 3.25), (8.0, 10.0)])

    def test_negative_start_is_clamped(self):
        log = "silence_start: -0.01\nsilence_end: 1 | silence_duration: 1.01\n"
        self.assertEqual(parse_silences(log, 5.0), [(0.0, 1.0)])

    def test_equals_separator_from_docs(self):
        log = "silence_start=2\nsilence_end=4 | silence_duration=2\n"
        self.assertEqual(parse_silences(log, 5.0), [(2.0, 4.0)])

    def test_unrelated_lines_ignored(self):
        self.assertEqual(parse_silences("Stream #0:0: Audio: aac\n", 5.0), [])


class DetectSilencesTest(unittest.TestCase):
    def test_runs_silencedetect_and_parses_stderr(self):
        with mock.patch("shared.api.silence.run") as run:
            run.return_value.stderr = "silence_start: 1\nsilence_end: 2 | silence_duration: 1\n"
            self.assertEqual(detect_silences("in.mp4", -35.0, 0.5, 10.0), [(1.0, 2.0)])
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("-af") + 1], "silencedetect=noise=-35.0dB:d=0.5")


if __name__ == "__main__":
    unittest.main()
