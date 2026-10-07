import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx2 as httpx
import openai

from shared.api import TranscriptionError, transcribe


def verbose_response():
    return SimpleNamespace(
        words=[SimpleNamespace(word="이제", start=0.5, end=0.8)],
        segments=[SimpleNamespace(start=0.0, end=1.0, text=" 이제 시작")],
    )


class TranscribeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.audio = Path(self._tmp.name) / "a.mp3"
        self.audio.write_bytes(b"mp3")

    def tearDown(self):
        self._tmp.cleanup()

    def test_requests_word_timestamps_in_korean_and_converts_result(self):
        with mock.patch("openai.OpenAI") as client_cls:
            create = client_cls.return_value.audio.transcriptions.create
            create.return_value = verbose_response()
            result = transcribe(self.audio, "sk-test")
        client_cls.assert_called_once_with(api_key="sk-test", max_retries=4)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], "whisper-1")
        self.assertEqual(kwargs["response_format"], "verbose_json")
        self.assertIn("word", kwargs["timestamp_granularities"])
        self.assertEqual(kwargs["language"], "ko")
        self.assertNotIn("prompt", kwargs)
        self.assertEqual(result["words"], [{"word": "이제", "start": 0.5, "end": 0.8}])
        self.assertEqual(result["segments"], [{"start": 0.0, "end": 1.0, "text": " 이제 시작"}])

    def test_prompt_is_sent_when_given(self):
        with mock.patch("openai.OpenAI") as client_cls:
            create = client_cls.return_value.audio.transcriptions.create
            create.return_value = verbose_response()
            transcribe(self.audio, "sk-test", prompt="앞 청크 문맥")
        self.assertEqual(create.call_args.kwargs["prompt"], "앞 청크 문맥")

    def test_api_error_is_wrapped(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
        error = openai.APIConnectionError(request=request)
        with mock.patch("openai.OpenAI") as client_cls:
            client_cls.return_value.audio.transcriptions.create.side_effect = error
            with self.assertRaises(TranscriptionError) as ctx:
                transcribe(self.audio, "sk-test")
        self.assertIn("Whisper API 호출 실패", str(ctx.exception))

    def test_auth_error_mentions_api_key(self):
        response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com"))
        error = openai.AuthenticationError("bad key", response=response, body=None)
        with mock.patch("openai.OpenAI") as client_cls:
            client_cls.return_value.audio.transcriptions.create.side_effect = error
            with self.assertRaises(TranscriptionError) as ctx:
                transcribe(self.audio, "sk-bad")
        self.assertIn("API 키", str(ctx.exception))

    def test_oversized_file_is_rejected_before_upload(self):
        with mock.patch("shared.api.whisper.MAX_UPLOAD_BYTES", 1), mock.patch("openai.OpenAI") as client_cls:
            with self.assertRaises(TranscriptionError):
                transcribe(self.audio, "sk-test")
        client_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
