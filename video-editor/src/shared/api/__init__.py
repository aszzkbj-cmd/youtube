"""외부 도구(ffmpeg/ffprobe, OpenAI Whisper) 래퍼 Public API."""

from .ffmpeg import (
    CommandError,
    ToolNotFoundError,
    has_audio,
    probe_duration,
    require_tools,
    run,
)
from .segments import concat_segments, extract_segment
from .silence import detect_silences
from .whisper import TranscriptionError, transcribe

__all__ = [
    "CommandError",
    "ToolNotFoundError",
    "TranscriptionError",
    "concat_segments",
    "detect_silences",
    "extract_segment",
    "has_audio",
    "probe_duration",
    "require_tools",
    "run",
    "transcribe",
]
