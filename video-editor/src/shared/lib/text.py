import unicodedata


def display_width(text: str) -> int:
    """터미널 표시 폭. 한글 등 전각 문자는 2칸으로 센다."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def ljust_display(text: str, width: int) -> str:
    """전각 문자를 고려해 표시 폭 width가 되도록 오른쪽을 공백으로 채운다."""
    return text + " " * max(0, width - display_width(text))
