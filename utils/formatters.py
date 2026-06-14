from __future__ import annotations

from typing import Any


def format_error_message(error: Exception) -> str:
    """사용자 화면에 표시할 오류 메시지를 너무 길지 않게 정리한다."""
    message = str(error)
    if not message:
        return "알 수 없는 오류가 발생했습니다."
    return message[:500]


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default
