from __future__ import annotations

from datetime import datetime

from config import KST


def now_kst() -> datetime:
    """현재 시간을 KST 기준 timezone-aware datetime으로 반환한다."""
    return datetime.now(KST)
