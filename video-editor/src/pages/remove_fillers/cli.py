"""remove-fillers 커맨드: 인자 파싱, 처리 흐름, 결과 출력."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from shared.api import (
    CommandError,
    ToolNotFoundError,
    TranscriptionError,
    concat_segments,
    extract_segment,
    has_audio,
    probe_duration,
    require_tools,
)
from shared.config import load_dotenv
from shared.lib import display_width, format_time, ljust_display

from .api import load_cached_transcript, save_cached_transcript, transcribe_video
from .model import (
    DEFAULT_MARGIN_AFTER,
    DEFAULT_MARGIN_BEFORE,
    DEFAULT_PADDING,
    Filler,
    compute_cuts,
    compute_keep_segments,
    detect_fillers,
    estimate_result_duration,
    parse_fillers,
    parse_transcript,
)

TEMP_PREFIX = "remove_fillers_"
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/pages/remove_fillers/cli.py → 프로젝트 루트
DEFAULT_FILLERS_FILE = PROJECT_ROOT / "fillers.txt"


class UsageError(Exception):
    """사용자에게 이유를 안내하고 종료해야 하는 상황."""


def default_output_path(src: Path) -> Path:
    return src.with_name(f"{src.stem}_no_fillers.mp4")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="remove_fillers.py",
        description="영상에서 간투사(filler words)를 감지해 제거합니다 (ffmpeg, OpenAI API 키 필요).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="입력 영상 경로")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="출력 경로 (기본: {원본이름}_no_fillers.mp4)")
    parser.add_argument("--api-key", default=None,
                        help="OpenAI API 키 (기본: 환경변수 또는 .env의 OPENAI_API_KEY)")
    parser.add_argument("--fillers-file", type=Path, default=None,
                        help="간투사 사전 (한 줄에 하나, 기본: 스크립트 옆 fillers.txt)")
    parser.add_argument("--margin-before", type=float, default=DEFAULT_MARGIN_BEFORE,
                        help="간투사 시작 전 함께 제거할 여백 (초)")
    parser.add_argument("--margin-after", type=float, default=DEFAULT_MARGIN_AFTER,
                        help="간투사 끝 후 함께 제거할 여백 (초)")
    parser.add_argument("--padding", type=float, default=DEFAULT_PADDING,
                        help="이어 붙이는 구간 사이에 넣을 무음 길이 (초, 재인코딩 모드에서만)")
    parser.add_argument("--dry-run", action="store_true",
                        help="영상을 편집하지 않고 감지 결과와 예상 단축 시간만 출력")
    parser.add_argument("--no-reencode", action="store_true",
                        help="-c copy로 자르기 (빠르지만 키프레임 단위로 잘려 부정확, padding 미적용)")
    parser.add_argument("--no-cache", action="store_true",
                        help="저장된 전사 결과({원본이름}.transcript.json)를 무시하고 Whisper를 다시 호출")
    args = parser.parse_args(argv)

    if min(args.margin_before, args.margin_after, args.padding) < 0:
        parser.error("margin/padding 값은 0 이상이어야 합니다.")
    return args


def load_filler_words(path: Path | None) -> set[str]:
    path = path or DEFAULT_FILLERS_FILE
    if not path.is_file():
        raise UsageError(f"간투사 사전을 찾을 수 없습니다: {path}\n"
                         "fillers.txt를 생성하고 간투사를 한 줄에 하나씩 입력하세요")
    fillers = parse_fillers(path.read_text(encoding="utf-8-sig"))
    if not fillers:
        raise UsageError(f"간투사 사전이 비어 있습니다: {path}\n간투사를 한 줄에 하나씩 입력하세요")
    return fillers


def resolve_api_key(cli_key: str | None) -> str:
    if cli_key:
        return cli_key
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(Path.cwd() / ".env")
    if key := os.environ.get("OPENAI_API_KEY"):
        return key
    raise UsageError("OPENAI_API_KEY가 설정되지 않았습니다.\n"
                     f"  {PROJECT_ROOT / '.env'} 에 OPENAI_API_KEY=sk-... 를 추가하거나,\n"
                     "  환경변수로 설정하거나, --api-key 옵션으로 지정하세요.")


def get_transcript(src: Path, duration: float, args: argparse.Namespace, workdir: Path) -> dict:
    if not args.no_cache and (cached := load_cached_transcript(src)) is not None:
        print("저장된 전사 결과를 사용합니다 (다시 전사하려면 --no-cache).")
        return cached
    api_key = resolve_api_key(args.api_key)
    transcript = transcribe_video(src, duration, api_key, workdir, progress=print)
    try:
        path = save_cached_transcript(src, transcript)
        print(f"전사 결과 저장: {path}")
    except OSError as exc:
        print(f"참고: 전사 결과를 저장하지 못했습니다 ({exc})")
    return transcript


def print_fillers(fillers: list[Filler]) -> None:
    width = max([4, *(display_width(f.word.text.strip()) for f in fillers)])
    print(f"{'#':>4}  {ljust_display('시작', 11)}  {ljust_display('끝', 11)}  {ljust_display('단어', width)}  판정 근거")
    print(f"{'-' * 4}  {'-' * 11}  {'-' * 11}  {'-' * width}  {'-' * 20}")
    for n, f in enumerate(fillers, 1):
        w = f.word
        print(f"{n:>4}  {format_time(w.start)}  {format_time(w.end)}  "
              f"{ljust_display(w.text.strip(), width)}  {', '.join(f.reasons)}")
    counts = Counter(f.word.text.strip() for f in fillers)
    print("단어별: " + ", ".join(f"{word} {count}회" for word, count in counts.most_common()))


def print_durations(original: float, result: float, label: str) -> None:
    saved = original - result
    ratio = saved / original * 100 if original else 0.0
    print(f"원본 길이:   {format_time(original)}")
    print(f"{label}:   {format_time(result)}")
    print(f"단축 시간:   {format_time(saved)} ({ratio:.1f}%)")


def render(src: Path, keep: list[tuple[float, float]], output: Path, reencode: bool, padding: float) -> None:
    with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as tmp:
        workdir = Path(tmp)
        suffix = ".mp4" if reencode else (src.suffix or ".mp4")
        parts: list[Path] = []
        for i, (start, end) in enumerate(keep):
            part = workdir / f"seg_{i:04d}{suffix}"
            pad = padding if i < len(keep) - 1 else 0.0  # 구간 "사이"에만 넣는다
            print(f"\r구간 추출 중... {i + 1}/{len(keep)}", end="", flush=True)
            extract_segment(src, start, end, part, reencode, pad)
            parts.append(part)
        print()
        print("병합 중...")
        concat_segments(parts, output, workdir)


def process(args: argparse.Namespace) -> None:
    require_tools()

    src: Path = args.input
    if not src.is_file():
        raise UsageError(f"입력 파일을 찾을 수 없습니다: {src}")
    output: Path = args.output or default_output_path(src)
    if not args.dry_run and output.resolve() == src.resolve():
        raise UsageError("출력 경로가 입력 파일과 같습니다. 다른 --output 경로를 지정하세요.")
    filler_words = load_filler_words(args.fillers_file)

    duration = probe_duration(src)
    if not has_audio(src):
        raise UsageError("오디오 트랙이 없어 음성을 인식할 수 없습니다.")

    with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as tmp:
        transcript = get_transcript(src, duration, args, Path(tmp))

    words, segments = parse_transcript(transcript, duration)
    fillers = detect_fillers(words, filler_words, segments)
    print(f"인식된 단어: {len(words)}개 / 감지된 간투사: {len(fillers)}개")

    if not fillers:
        print("간투사 없음" + ("" if args.dry_run else " - 원본을 그대로 복사합니다."))
        if not args.dry_run:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, output)
            print(f"저장 위치: {output}")
        return

    print()
    print_fillers(fillers)
    print()

    reencode = not args.no_reencode
    padding = args.padding if reencode else 0.0
    cuts = compute_cuts(fillers, words, duration, args.margin_before, args.margin_after)
    keep = compute_keep_segments(cuts, duration)
    if not keep:
        raise UsageError("제거 후 남는 구간이 없습니다. --margin-before/--margin-after 값을 줄여 보세요.")

    if args.dry_run:
        print_durations(duration, estimate_result_duration(keep, padding), "예상 길이")
        print(f"제거 구간: {len(cuts)}개 / 유지 구간: {len(keep)}개 (dry-run: 영상은 만들지 않았습니다)")
        return

    if not reencode:
        print("경고: copy 모드는 각 구간이 직전 키프레임부터 잘려 앞부분이 중복됩니다. 간투사처럼 짧은 컷에서는\n"
              "      제거량보다 중복이 커져 결과가 원본보다 길어질 수 있습니다. --padding도 적용되지 않습니다.")

    output.parent.mkdir(parents=True, exist_ok=True)
    render(src, keep, output, reencode, padding)

    print()
    print_durations(duration, probe_duration(output), "결과 길이")
    print(f"제거 구간: {len(cuts)}개 / 유지 구간: {len(keep)}개")
    print(f"저장 위치: {output}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        process(args)
    except (ToolNotFoundError, CommandError, TranscriptionError, UsageError) as exc:
        print(f"\n[오류] {exc}", file=sys.stderr)
        return 1
    return 0
