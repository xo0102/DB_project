from __future__ import annotations

from typing import Optional

import streamlit as st
from supabase import create_client


def read_secret(key: str) -> Optional[str]:
    """Streamlit secrets에서 값을 안전하게 읽는다."""
    try:
        value = st.secrets[key]
        return str(value).strip() if value else None
    except Exception:
        return None


def get_supabase_client():
    """
    Supabase 클라이언트를 생성한다.

    - URL/KEY는 반드시 .streamlit/secrets.toml에서 읽는다.
    - 로그인 후 저장된 access_token, refresh_token이 있으면 세션을 복원한다.
    - secrets.toml이 없어도 앱 전체가 바로 멈추지 않도록 None을 반환한다.
    """
    url = read_secret("SUPABASE_URL")
    key = read_secret("SUPABASE_KEY")

    if not url or not key:
        return None

    try:
        client = create_client(url, key)

        access_token = st.session_state.get("access_token")
        refresh_token = st.session_state.get("refresh_token")

        if access_token and refresh_token:
            try:
                client.auth.set_session(access_token, refresh_token)
            except Exception:
                # 세션 복원 실패 시 로그인 정보만 제거하고 앱은 계속 실행한다.
                st.session_state.pop("access_token", None)
                st.session_state.pop("refresh_token", None)
                st.session_state.pop("user_id", None)
                st.session_state.pop("user_email", None)

        return client

    except Exception as e:
        st.session_state["supabase_client_error"] = str(e)
        return None


def has_supabase(client) -> bool:
    return client is not None


def show_supabase_warning() -> None:
    st.warning(
        "Supabase 연결 정보가 아직 설정되지 않았습니다. "
        "`.streamlit/secrets.toml` 파일을 만들고 `SUPABASE_URL`, `SUPABASE_KEY` 값을 입력해주세요."
    )
