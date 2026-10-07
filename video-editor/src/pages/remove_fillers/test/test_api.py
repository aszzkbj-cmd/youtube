import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pages.remove_fillers.api import (
    CHUNK_SECONDS,
    PROMPT_CHARS,
    build_audio_extract_command,
    cache_path,
    load_cached_transcript,
    offset_transcript,
    plan_chunks,
    save_cached_transcript,
    transcribe_video,
)
from shared.api import TranscriptionError


class PlanChunksTest(unittest.TestCase):
    def test_short_video_is_single_chunk(self):
        self.assertEqual(plan_chunks(100.0), [(0.0, 100.0)])
        self.assertEqual(plan_chunks(CHUNK_SECONDS), [(0.0, CHUNK_SECONDS)])

    def test_default_chunk_is_five_minutes(self):
        self.assertEqual(CHUNK_SECONDS, 300.0)

    def test_long_video_without_silence_splits_at_chunk_length(self):
        self.assertEqual(plan_chunks(700.0), [(0.0, 300.0), (300.0, 300.0), (600.0, 100.0)])

    def test_cuts_at_middle_of_silence_closest_to_target(self):
        # 300초 목표 직전 60초 안 무음 2개 → 더 가까운 [290, 292]의 가운데 291에서 자른다
        chunks = plan_chunks(500.0, silences=[(250.0, 252.0), (290.0, 292.0)])
        self.assertEqual(chunks, [(0.0, 291.0), (291.0, 209.0)])

    def test_ignores_silences_outside_search_window(self):
        # 230초(목표-70)와 310초(목표 이후)는 범위 밖 → 300초에서 강제 분할
        chunks = plan_chunks(500.0, silences=[(229.0, 231.0), (309.0, 311.0)])
        self.assertEqual(chunks, [(0.0, 300.0), (300.0, 200.0)])

    def test_next_target_is_measured_from_previous_cut(self):
        chunks = plan_chunks(700.0, silences=[(279.0, 281.0), (570.0, 572.0)])
        # 1번째 경계 280 → 2번째 목표 580, 무음 가운데 571에서 자른다
        self.assertEqual(chunks, [(0.0, 280.0), (280.0, 291.0), (571.0, 129.0)])


def fake_extract(cmd):
    Path(cmd[-1]).write_bytes(b"mp3")


def part(text, start=1.0):
    return {"words": [{"word": text, "start": start, "end": start + 0.5}],
            "segments": [{"start": start, "end": start + 0.5, "text": f" {text}"}]}


class TranscribeVideoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workdir = Path(self._tmp.name)
        self.patches = {
            name: mock.patch(f"pages.remove_fillers.api.{name}")
            for name in ("run", "detect_silences", "transcribe")
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        self.mocks["run"].side_effect = fake_extract
        self.mocks["detect_silences"].return_value = []

    def tearDown(self):
        for p in self.patches.values():
            p.stop()
        self._tmp.cleanup()

    def test_short_video_skips_silence_detection_and_prompt(self):
        self.mocks["transcribe"].return_value = part("안녕")
        result = transcribe_video(Path("in.mp4"), 100.0, "sk", self.workdir)
        self.mocks["detect_silences"].assert_not_called()
        self.assertIsNone(self.mocks["transcribe"].call_args.kwargs["prompt"])
        self.assertEqual(result["words"][0]["start"], 1.0)

    def test_long_video_offsets_and_passes_previous_text_as_prompt(self):
        long_text = "가" * (PROMPT_CHARS + 50) + "끝"
        self.mocks["transcribe"].side_effect = [part(long_text), part("둘째")]
        result = transcribe_video(Path("in.mp4"), 500.0, "sk", self.workdir)

        self.mocks["detect_silences"].assert_called_once()
        prompts = [c.kwargs["prompt"] for c in self.mocks["transcribe"].call_args_list]
        self.assertIsNone(prompts[0])
        self.assertEqual(len(prompts[1]), PROMPT_CHARS)
        self.assertTrue(prompts[1].endswith("끝"))
        self.assertEqual([w["start"] for w in result["words"]], [1.0, 301.0])

    def test_failure_names_the_chunk(self):
        self.mocks["transcribe"].side_effect = [part("하나"), TranscriptionError("Whisper API 호출 실패: SSL")]
        with self.assertRaises(TranscriptionError) as ctx:
            transcribe_video(Path("in.mp4"), 500.0, "sk", self.workdir)
        self.assertIn("2/2", str(ctx.exception))
        self.assertIn("Whisper API 호출 실패", str(ctx.exception))


class AudioCommandTest(unittest.TestCase):
    def test_extracts_mono_low_bitrate_mp3(self):
        cmd = build_audio_extract_command(Path("in.mp4"), 1800.0, 400.0, Path("a.mp3"))
        self.assertLess(cmd.index("-ss"), cmd.index("-i"))
        self.assertEqual(cmd[cmd.index("-ss") + 1], "1800.000")
        self.assertEqual(cmd[cmd.index("-t") + 1], "400.000")
        self.assertIn("-vn", cmd)
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "libmp3lame")
        self.assertEqual(cmd[cmd.index("-ac") + 1], "1")
        self.assertEqual(cmd[-1], "a.mp3")


class OffsetTest(unittest.TestCase):
    def test_adds_chunk_start(self):
        part = {"words": [{"word": "a", "start": 1.0, "end": 2.0}],
                "segments": [{"start": 0.5, "end": 2.0, "text": "a"}]}
        moved = offset_transcript(part, 1800.0)
        self.assertEqual(moved["words"][0], {"word": "a", "start": 1801.0, "end": 1802.0})
        self.assertEqual(moved["segments"][0]["start"], 1800.5)


class CacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.src = Path(self._tmp.name) / "영상 1.mp4"
        self.src.write_bytes(b"video")

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip(self):
        transcript = {"words": [{"word": "이제", "start": 0.0, "end": 0.3}], "segments": []}
        path = save_cached_transcript(self.src, transcript)
        self.assertEqual(path, cache_path(self.src))
        self.assertEqual(path.name, "영상 1.transcript.json")
        self.assertEqual(load_cached_transcript(self.src), transcript)

    def test_changed_source_invalidates_cache(self):
        save_cached_transcript(self.src, {"words": [], "segments": []})
        self.src.write_bytes(b"different video")
        self.assertIsNone(load_cached_transcript(self.src))

    def test_missing_or_broken_cache(self):
        self.assertIsNone(load_cached_transcript(self.src))
        cache_path(self.src).write_text("{broken", encoding="utf-8")
        self.assertIsNone(load_cached_transcript(self.src))


if __name__ == "__main__":
    unittest.main()
