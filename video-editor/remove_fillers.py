"""영상에서 간투사(filler words)를 감지해 제거하는 CLI (SPEC-002).

사용법:
    uv run python remove_fillers.py <input_video> [--output PATH] [--api-key KEY]
        [--fillers-file TXT] [--margin-before SEC] [--margin-after SEC] [--padding SEC]
        [--dry-run] [--no-reencode] [--no-cache]

구현은 src/ (FSD 구조)에 있으며, 이 파일은 실행 진입점만 담당한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from app import remove_fillers  # noqa: E402

if __name__ == "__main__":
    sys.exit(remove_fillers())
