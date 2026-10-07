"""최소한의 .env 로더 (python-dotenv 의존성 없이 KEY=VALUE 형식만 지원)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """path의 KEY=VALUE 줄을 환경변수로 설정한다. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)
