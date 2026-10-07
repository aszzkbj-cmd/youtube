"""specs/SPEC-002-remove-fillers/acceptance.md 인수 기준 테스트.

Whisper API는 비용과 키가 필요하므로 shared.api.transcribe 호출 지점을 모킹하고,
오디오 추출·구간 추출·병합은 lavfi로 만든 실제 영상으로 검증한다.
ffmpeg가 없는 환경에서는 실제 영상 테스트를 skip한다.
"""

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pages.remove_fillers import main
from pages.remove_fillers.cli import TEMP_PREFIX
from shared.api import TranscriptionError, probe_duration

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

# test_model.FIXTURE_WORDS와 같은 전사 결과 (Whisper 응답 형태)
FIXTURE_TRANSCRIPT = {
    "words": [
        {"word": "안녕하세요", "start": 0.2, "end": 1.0},
        {"word": "이제", "start": 1.5, "end": 1.8},
        {"word": "시작합니다", "start": 1.9, "end": 2.6},
        {"word": "그래서", "start": 2.65, "end": 2.9},
        {"word": "진짜", "start": 2.95, "end": 3.5},
        {"word": "좀", "start": 3.55, "end": 3.7},
        {"word": "어려워요", "start": 3.75, "end": 4.5},
    ],
    "segments": [{"start": 0.2, "end": 4.5, "text": " 안녕하세요 이제 시작합니다. 그래서 진짜 좀 어려워요."}],
}
TRANSCRIBE = "pages.remove_fillers.api.transcribe"
NO_DOTENV = mock.patch("pages.remove_fillers.cli.load_dotenv")


def invoke(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def leftover_temp_dirs() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*")}


def fake_transcribe(audio: Path, api_key: str, language: str = "ko", prompt: str | None = None) -> dict:
    assert audio.suffix == ".mp3" and audio.stat().st_size > 0, "오디오가 mp3로 추출되어야 한다"
    return FIXTURE_TRANSCRIPT


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe가 없어 인수 테스트를 건너뜀")
class AcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AC-12: 한글과 공백이 들어간 경로에서 모든 시나리오를 실행한다
        cls._tmp = tempfile.TemporaryDirectory(prefix="rf_acceptance_")
        cls.dir = Path(cls._tmp.name) / "테스트 폴더"
        cls.dir.mkdir()
        cls.speech = cls.dir / "speech.mp4"
        cls.noaudio = cls.dir / "noaudio.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=6",
               "-f", "lavfi", "-i", "sine=f=440:d=6",
               "-c:v", "libx264", "-g", "30", "-c:a", "aac", "-shortest", str(cls.speech))
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=3",
               "-c:v", "libx264", str(cls.noaudio))
        cls.fillers = cls.dir / "fillers.txt"
        cls.fillers.write_text("이제\n그래서\n좀\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.temp_before = leftover_temp_dirs()
        self.env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
        self.env.start()
        NO_DOTENV.start()

    def tearDown(self):
        NO_DOTENV.stop()
        self.env.stop()
        # AC-10: 성공/실패와 관계없이 임시 디렉터리가 남지 않는다
        self.assertEqual(leftover_temp_dirs() - self.temp_before, set())

    def run_fillers(self, *argv: str) -> tuple[int, str, str]:
        with mock.patch(TRANSCRIBE, side_effect=fake_transcribe):
            return invoke(str(self.speech), "--fillers-file", str(self.fillers), "--no-cache", *argv)

    def test_ac1_ac3_reencode_removes_fillers_with_padding(self):
        expected = self.dir / "speech_no_fillers.mp4"
        code, stdout, _ = self.run_fillers()
        self.assertEqual(code, 0)
        self.assertTrue(expected.is_file())
        # 유지 구간 [0,1.4] + [1.9,2.6] + [2.95,6] + padding 0.05 × 2 = 5.25
        self.assertAlmostEqual(probe_duration(expected), 5.25, delta=0.1)
        for text in ("이제", "그래서", "원본 길이", "결과 길이", "단축 시간"):
            self.assertIn(text, stdout)

    def test_ac2_dry_run_prints_table_without_output(self):
        out = self.dir / "ac2.mp4"
        code, stdout, _ = self.run_fillers("--dry-run", "--output", str(out))
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())
        self.assertIn("감지된 간투사: 2개", stdout)
        self.assertIn("문장 시작", stdout)
        self.assertIn("예상 길이:   00:00:05.25", stdout)
        self.assertIn("단축 시간:   00:00:00.75", stdout)

    def test_ac4_no_reencode_mode(self):
        # copy 모드는 키프레임(이 fixture는 1초 GOP)부터 잘리므로 길이가 오히려 늘 수 있다 — 생성과 경고만 확인
        out = self.dir / "ac4.mp4"
        code, stdout, _ = self.run_fillers("--no-reencode", "--output", str(out))
        self.assertEqual(code, 0)
        self.assertGreater(probe_duration(out), 0)
        self.assertIn("copy 모드", stdout)
        self.assertIn("길어질 수 있습니다", stdout)

    def test_ac5_no_fillers_copies_original(self):
        out = self.dir / "ac5.mp4"
        other = self.dir / "other_fillers.txt"
        other.write_text("아무튼\n", encoding="utf-8")
        with mock.patch(TRANSCRIBE, side_effect=fake_transcribe):
            code, stdout, _ = invoke(str(self.speech), "--fillers-file", str(other),
                                     "--no-cache", "--output", str(out))
        self.assertEqual(code, 0)
        self.assertIn("간투사 없음", stdout)
        self.assertEqual(out.read_bytes(), self.speech.read_bytes())

    def test_ac6_missing_fillers_file(self):
        code, _, stderr = invoke(str(self.speech), "--fillers-file", str(self.dir / "nope.txt"))
        self.assertEqual(code, 1)
        self.assertIn("fillers.txt를 생성하고 간투사를 한 줄에 하나씩 입력하세요", stderr)

    def test_ac7_missing_api_key(self):
        with mock.patch.dict(os.environ), mock.patch(TRANSCRIBE) as t:
            del os.environ["OPENAI_API_KEY"]
            code, _, stderr = invoke(str(self.speech), "--fillers-file", str(self.fillers), "--no-cache")
        self.assertEqual(code, 1)
        self.assertIn("OPENAI_API_KEY", stderr)
        t.assert_not_called()

    def test_ac7_api_key_option_overrides_env(self):
        with mock.patch(TRANSCRIBE, side_effect=fake_transcribe) as t:
            invoke(str(self.speech), "--fillers-file", str(self.fillers), "--no-cache",
                   "--dry-run", "--api-key", "sk-option")
        self.assertEqual(t.call_args.args[1], "sk-option")

    def test_ac8_whisper_failure(self):
        with mock.patch(TRANSCRIBE, side_effect=TranscriptionError("Whisper API 호출 실패: 500")):
            code, _, stderr = invoke(str(self.speech), "--fillers-file", str(self.fillers),
                                     "--no-cache", "--output", str(self.dir / "ac8.mp4"))
        self.assertEqual(code, 1)
        self.assertIn("Whisper API 호출 실패", stderr)
        self.assertFalse((self.dir / "ac8.mp4").exists())

    def test_ac9_no_audio_track(self):
        code, _, stderr = invoke(str(self.noaudio), "--fillers-file", str(self.fillers))
        self.assertEqual(code, 1)
        self.assertIn("오디오 트랙", stderr)

    def test_ac11_refuses_to_overwrite_input(self):
        before = self.speech.read_bytes()
        code, _, stderr = invoke(str(self.speech), "--fillers-file", str(self.fillers),
                                 "--output", str(self.speech))
        self.assertEqual(code, 1)
        self.assertIn("입력 파일과 같습니다", stderr)
        self.assertEqual(self.speech.read_bytes(), before)

    def test_ac13_transcript_cache_skips_second_api_call(self):
        src = self.dir / "cached.mp4"
        shutil.copy2(self.speech, src)
        with mock.patch(TRANSCRIBE, side_effect=fake_transcribe) as t:
            invoke(str(src), "--fillers-file", str(self.fillers), "--dry-run")
            code, stdout, _ = invoke(str(src), "--fillers-file", str(self.fillers),
                                     "--output", str(self.dir / "ac13.mp4"))
        self.assertEqual(code, 0)
        self.assertEqual(t.call_count, 1)
        self.assertIn("저장된 전사 결과", stdout)
        self.assertTrue((self.dir / "cached.transcript.json").is_file())


class MockedAcceptanceTest(unittest.TestCase):
    def test_ac14_ffmpeg_not_installed(self):
        with mock.patch("shared.api.ffmpeg.shutil.which", return_value=None):
            code, _, stderr = invoke("whatever.mp4")
        self.assertEqual(code, 1)
        self.assertIn("winget install Gyan.FFmpeg", stderr)

    def test_ac15_subprocess_failure_prints_command_and_stderr(self):
        failed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Invalid data found")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.mp4"
            src.write_bytes(b"x")
            fillers = Path(d) / "fillers.txt"
            fillers.write_text("이제\n", encoding="utf-8")
            with mock.patch("shared.api.ffmpeg.shutil.which", return_value="/bin/x"), \
                 mock.patch("shared.api.ffmpeg.subprocess.run", return_value=failed):
                code, _, stderr = invoke(str(src), "--fillers-file", str(fillers))
        self.assertEqual(code, 1)
        self.assertIn("ffprobe", stderr)
        self.assertIn("Invalid data found", stderr)


if __name__ == "__main__":
    unittest.main()
