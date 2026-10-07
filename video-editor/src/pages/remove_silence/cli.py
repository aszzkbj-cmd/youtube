"""remove-silence 커맨드: 인자 파싱, 처리 흐름, 결과 출력."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from shared.api import (
    CommandError,
    ToolNotFoundError,
    concat_segments,
    detect_silences,
    extract_segment,
    has_audio,
    probe_duration,
    require_tools,
)
from shared.lib import format_time

from .model import (
    DEFAULT_MARGIN_AFTER,
    DEFAULT_MARGIN_BEFORE,
    DEFAULT_MIN_SILENCE,
    DEFAULT_THRESHOLD_DB,
    compute_keep_segments,
)

TEMP_PREFIX = "remove_silence_"


class UsageError(Exception):
    """사용자에게 이유를 안내하고 종료해야 하는 상황."""


def default_output_path(src: Path) -> Path:
    return src.with_name(f"{src.stem}_no_silence.mp4")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="remove_silence.py",
        description="영상에서 무음 구간을 제거합니다 (ffmpeg 필요).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="입력 영상 경로")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="출력 경로 (기본: {원본이름}_no_silence.mp4)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_DB,
                        help="무음 판정 기준 (dB)")
    parser.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE,
                        help="이 길이(초) 이상인 무음만 제거")
    parser.add_argument("--margin-before", type=float, default=DEFAULT_MARGIN_BEFORE,
                        help="음성 시작 전 보존할 여백 (초)")
    parser.add_argument("--margin-after", type=float, default=DEFAULT_MARGIN_AFTER,
                        help="음성 끝 후 보존할 여백 (초)")
    parser.add_argument("--reencode", action="store_true",
                        help="libx264/aac로 재인코딩 (프레임 단위 정밀 컷, 코덱 불일치 방지)")
    args = parser.parse_args(argv)

    if args.min_silence <= 0:
        parser.error("--min-silence는 0보다 커야 합니다.")
    if args.margin_before < 0 or args.margin_after < 0:
        parser.error("margin 값은 0 이상이어야 합니다.")
    return args


def process(args: argparse.Namespace) -> None:
    require_tools()

    src: Path = args.input
    if not src.is_file():
        raise UsageError(f"입력 파일을 찾을 수 없습니다: {src}")
    output: Path = args.output or default_output_path(src)
    if output.resolve() == src.resolve():
        raise UsageError("출력 경로가 입력 파일과 같습니다. 다른 --output 경로를 지정하세요.")

    duration = probe_duration(src)
    if not has_audio(src):
        raise UsageError("오디오 트랙이 없어 무음을 감지할 수 없습니다.")

    print(f"무음 감지 중... (threshold={args.threshold}dB, min-silence={args.min_silence}s)")
    silences = detect_silences(src, args.threshold, args.min_silence, duration)

    output.parent.mkdir(parents=True, exist_ok=True)
    if not silences:
        print("무음 구간 없음 - 원본을 그대로 복사합니다.")
        shutil.copy2(src, output)
        print(f"저장 위치: {output}")
        return

    segments = compute_keep_segments(silences, duration, args.margin_before, args.margin_after)
    if not segments:
        raise UsageError("영상 전체가 무음으로 판정되었습니다. --threshold 값을 낮춰 보세요.")

    if not args.reencode:
        print("참고: copy 모드는 키프레임 단위로 잘려 컷 위치가 부정확할 수 있습니다. "
              "정밀한 컷이 필요하면 --reencode를 사용하세요.")

    with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as tmp:
        workdir = Path(tmp)
        suffix = ".mp4" if args.reencode else (src.suffix or ".mp4")
        parts: list[Path] = []
        for i, (start, end) in enumerate(segments):
            part = workdir / f"seg_{i:04d}{suffix}"
            print(f"\r구간 추출 중... {i + 1}/{len(segments)}", end="", flush=True)
            extract_segment(src, start, end, part, args.reencode)
            parts.append(part)
        print()
        print("병합 중...")
        concat_segments(parts, output, workdir)

    result_duration = probe_duration(output)
    saved = duration - result_duration
    ratio = saved / duration * 100 if duration else 0.0
    print()
    print(f"원본 길이:   {format_time(duration)}")
    print(f"결과 길이:   {format_time(result_duration)}")
    print(f"단축 시간:   {format_time(saved)} ({ratio:.1f}%)")
    print(f"감지된 무음 구간: {len(silences)}개 / 유지 구간: {len(segments)}개")
    print(f"저장 위치: {output}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        process(args)
    except (ToolNotFoundError, CommandError, UsageError) as exc:
        print(f"\n[오류] {exc}", file=sys.stderr)
        return 1
    return 0
