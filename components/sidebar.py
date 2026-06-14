from __future__ import annotations

import streamlit as st

from config import APP_SUBTITLE, APP_TITLE, MENU_ITEMS
from services.auth_service import get_logged_in_email, get_logged_in_user_id, is_logged_in


def render_sidebar() -> str:
    st.sidebar.title(APP_TITLE)
    st.sidebar.caption(APP_SUBTITLE)

    if is_logged_in():
        st.sidebar.success("로그인 상태")
        st.sidebar.caption(get_logged_in_email() or get_logged_in_user_id())
    else:
        st.sidebar.info("로그아웃 상태")

    return st.sidebar.radio("메뉴", MENU_ITEMS)
