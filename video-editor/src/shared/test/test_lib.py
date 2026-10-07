import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shared.config import load_dotenv
from shared.lib import display_width, format_time, ljust_display


class FormatTimeTest(unittest.TestCase):
    def test_formats_and_clamps_negative(self):
        self.assertEqual(format_time(3725.5), "01:02:05.50")
        self.assertEqual(format_time(-1), "00:00:00.00")


class DisplayWidthTest(unittest.TestCase):
    def test_hangul_counts_double(self):
        self.assertEqual(display_width("이제a"), 5)
        self.assertEqual(ljust_display("좀", 4), "좀  ")


class LoadDotenvTest(unittest.TestCase):
    def test_parses_quotes_comments_export_and_keeps_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".env"
            path.write_text(
                "# comment\nA_KEY='quoted'\nexport B_KEY=plain\nEXISTING=new\n\nnot a pair\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"EXISTING": "old"}, clear=True):
                load_dotenv(path)
                self.assertEqual(os.environ["A_KEY"], "quoted")
                self.assertEqual(os.environ["B_KEY"], "plain")
                self.assertEqual(os.environ["EXISTING"], "old")

    def test_missing_file_is_ignored(self):
        load_dotenv(Path("definitely-missing.env"))


if __name__ == "__main__":
    unittest.main()
