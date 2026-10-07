"""앱 진입점. 커맨드를 pages 슬라이스로 연결한다."""

from pages.remove_fillers import main as remove_fillers
from pages.remove_silence import main as remove_silence

__all__ = ["remove_fillers", "remove_silence"]
