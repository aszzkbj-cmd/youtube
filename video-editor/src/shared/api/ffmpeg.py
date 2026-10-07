"""ffmpeg/ffprobe CLI 공통 래퍼.

참고:
- ffprobe -show_entries: https://ffmpeg.org/ffprobe.html
- ffmpeg 공통 옵션: https://ffmpeg.org/ffmpeg.html#Main-options
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REQUIRED_TOOLS = ("ffmpeg", "ffprobe")

INSTALL_GUIDE = (
    "ffmpeg를 설치한 뒤 PATH에 추가하세요.\n"
    "  Windows: winget install Gyan.FFmpeg\n"
    "  macOS:   brew install ffmpeg\n"
    "  Linux:   sudo apt install ffmpeg"
)


class ToolNotFoundError(RuntimeError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"{', '.join(missing)}을(를) 찾을 수 없습니다. {INSTALL_GUIDE}")


class CommandError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"명령 실행 실패 (exit {returncode}):\n"
            f"  {subprocess.list2cmdline(cmd)}\n"
            f"{stderr.strip()}"
        )


def require_tools() -> None:
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        raise ToolNotFoundError(missing)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """명령을 실행하고, 실패하면 CommandError를 던진다.

    Windows 기본 인코딩(cp949)에서 ffmpeg 출력 디코딩이 깨지지 않도록 UTF-8로 읽는다.
    """
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise CommandError(cmd, result.returncode, result.stderr)
    return result


def probe_duration(path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise CommandError(["ffprobe", str(path)], 0, f"duration 값을 해석할 수 없습니다: {result.stdout!r}")


def has_audio(path: Path) -> bool:
    result = run([
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(path),
    ])
    return bool(result.stdout.strip())
