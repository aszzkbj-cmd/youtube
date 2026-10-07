"""specs/SPEC-001-remove-silence/acceptance.md 인수 기준 테스트.

AC-8, AC-9는 모킹으로, 나머지는 lavfi로 만든 실제 영상으로 검증한다.
ffmpeg가 없는 환경에서는 실제 영상 테스트를 skip한다.
"""

import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pages.remove_silence import main
from pages.remove_silence.cli import TEMP_PREFIX
from shared.api import probe_duration

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def invoke(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def leftover_temp_dirs() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*")}


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe가 없어 인수 테스트를 건너뜀")
class AcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AC-12: 한글과 공백이 들어간 경로에서 모든 시나리오를 실행한다
        cls._tmp = tempfile.TemporaryDirectory(prefix="rs_acceptance_")
        cls.dir = Path(cls._tmp.name) / "테스트 폴더"
        cls.dir.mkdir()
        cls.speech = cls.dir / "speech.mp4"
        cls.tone = cls.dir / "tone.mp4"
        cls.noaudio = cls.dir / "noaudio.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=6",
               "-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,3),1),0.5*sin(2*PI*440*t),0)':s=48000:d=6",
               "-c:v", "libx264", "-g", "30", "-c:a", "aac", "-shortest", str(cls.speech))
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=4",
               "-f", "lavfi", "-i", "sine=f=440:d=4",
               "-c:v", "libx264", "-c:a", "aac", "-shortest", str(cls.tone))
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=3",
               "-c:v", "libx264", str(cls.noaudio))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.temp_before = leftover_temp_dirs()

    def tearDown(self):
        # AC-11: 성공/실패와 관계없이 임시 디렉터리가 남지 않는다
        self.assertEqual(leftover_temp_dirs() - self.temp_before, set())

    def test_ac1_reencode_removes_silence_precisely(self):
        out = self.dir / "ac1.mp4"
        code, stdout, _ = invoke(str(self.speech), "--output", str(out), "--reencode")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(probe_duration(out), 2.75, delta=0.15)
        for label in ("원본 길이", "결과 길이", "단축 시간"):
            self.assertIn(label, stdout)

    def test_ac2_ac3_copy_mode_default_output_name(self):
        expected = self.dir / "speech_no_silence.mp4"
        code, stdout, _ = invoke(str(self.speech))
        self.assertEqual(code, 0)
        self.assertTrue(expected.is_file())
        self.assertLess(probe_duration(expected), 6.0)
        self.assertIn("--reencode", stdout)

    def test_ac4_no_silence_copies_original(self):
        out = self.dir / "ac4.mp4"
        code, stdout, _ = invoke(str(self.tone), "--output", str(out))
        self.assertEqual(code, 0)
        self.assertIn("무음 구간 없음", stdout)
        self.assertEqual(out.read_bytes(), self.tone.read_bytes())

    def test_ac5_no_audio_track(self):
        code, _, stderr = invoke(str(self.noaudio), "--output", str(self.dir / "ac5.mp4"))
        self.assertEqual(code, 1)
        self.assertIn("오디오 트랙", stderr)

    def test_ac6_missing_input(self):
        code, _, stderr = invoke(str(self.dir / "nope.mp4"))
        self.assertEqual(code, 1)
        self.assertIn("찾을 수 없습니다", stderr)

    def test_ac7_all_silence(self):
        out = self.dir / "ac7.mp4"
        code, _, stderr = invoke(str(self.speech), "--threshold", "10", "--output", str(out))
        self.assertEqual(code, 1)
        self.assertIn("--threshold", stderr)
        self.assertFalse(out.exists())

    def test_ac10_refuses_to_overwrite_input(self):
        before = self.speech.read_bytes()
        code, _, stderr = invoke(str(self.speech), "--output", str(self.speech))
        self.assertEqual(code, 1)
        self.assertIn("입력 파일과 같습니다", stderr)
        self.assertEqual(self.speech.read_bytes(), before)


class MockedAcceptanceTest(unittest.TestCase):
    def test_ac8_ffmpeg_not_installed(self):
        with mock.patch("shared.api.ffmpeg.shutil.which", return_value=None):
            code, _, stderr = invoke("whatever.mp4")
        self.assertEqual(code, 1)
        self.assertIn("winget install Gyan.FFmpeg", stderr)

    def test_ac9_subprocess_failure_prints_command_and_stderr(self):
        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Invalid data found")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            src = Path(f.name)
        try:
            with mock.patch("shared.api.ffmpeg.shutil.which", return_value="/bin/x"), \
                 mock.patch("shared.api.ffmpeg.subprocess.run", return_value=failed):
                code, _, stderr = invoke(str(src))
        finally:
            src.unlink()
        self.assertEqual(code, 1)
        self.assertIn("ffprobe", stderr)
        self.assertIn("Invalid data found", stderr)


if __name__ == "__main__":
    unittest.main()
