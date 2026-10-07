"""영상에서 무음 구간을 제거하는 CLI (SPEC-001).

사용법:
    uv run python remove_silence.py <input_video> [--output PATH] [--threshold dB]
        [--min-silence SEC] [--margin-before SEC] [--margin-after SEC] [--reencode]

구현은 src/ (FSD 구조)에 있으며, 이 파일은 실행 진입점만 담당한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from app import remove_silence  # noqa: E402

if __name__ == "__main__":
    sys.exit(remove_silence())
