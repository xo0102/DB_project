from __future__ import annotations

from typing import Optional

import streamlit as st


def read_secret(key: str) -> Optional[str]:
    """Streamlit secrets에서 문자열 값을 안전하게 읽는다."""
    try:
        value = st.secrets[key]
    except Exception:
        return None

    if value is None:
        return None

    text = str(value).strip()
    return text or None
