"""구간 추출과 병합: 여러 편집 커맨드가 공유하는 ffmpeg 호출.

참고:
- -ss / -t (입력 -to와 -t는 상호 배타, -t 우선): https://ffmpeg.org/ffmpeg.html#Main-options
- avoid_negative_ts: https://ffmpeg.org/ffmpeg-formats.html#Format-Options
- tpad / apad: https://ffmpeg.org/ffmpeg-filters.html#tpad , https://ffmpeg.org/ffmpeg-filters.html#apad
- concat demuxer (safe 기본값 1, 경로 이스케이프): https://ffmpeg.org/ffmpeg-formats.html#concat-1
"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg import run

REENCODE_ARGS = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k",
]
COPY_ARGS = ["-c", "copy", "-avoid_negative_ts", "make_zero"]


def build_extract_command(
    src: Path, start: float, end: float, out: Path, reencode: bool, pad: float = 0.0
) -> list[str]:
    """[start, end] 구간을 out으로 추출하는 명령.

    pad > 0이면 구간 끝에 pad초를 덧붙인다: 오디오는 무음(apad), 영상은 마지막 프레임 유지(tpad).
    필터가 필요하므로 재인코딩 모드에서만 쓸 수 있다.
    """
    if pad > 0 and not reencode:
        raise ValueError("pad는 재인코딩 모드에서만 사용할 수 있습니다.")
    filters = []
    if pad > 0:
        filters = [
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
            "-af", f"apad=pad_dur={pad:.3f}",
        ]
    return [
        "ffmpeg", "-hide_banner", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(src),
        "-t", f"{end - start + pad:.3f}",
        "-map", "0:v?", "-map", "0:a?",
        *filters,
        *(REENCODE_ARGS if reencode else COPY_ARGS),
        str(out),
    ]


def extract_segment(
    src: Path, start: float, end: float, out: Path, reencode: bool, pad: float = 0.0
) -> None:
    run(build_extract_command(src, start, end, out, reencode, pad))


def concat_entry(path: Path) -> str:
    # concat demuxer는 백슬래시를 이스케이프 문자로 해석하므로 슬래시로 바꾸고 ' 를 이스케이프
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def concat_segments(files: list[Path], output: Path, workdir: Path) -> None:
    list_file = workdir / "concat_list.txt"
    list_file.write_text("\n".join(concat_entry(f) for f in files) + "\n", encoding="utf-8")
    run([
        "ffmpeg", "-hide_banner", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output),
    ])
