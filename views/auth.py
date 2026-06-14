from __future__ import annotations

import streamlit as st

from db.client import has_supabase, show_supabase_warning
from services.auth_service import (
    get_logged_in_email,
    get_logged_in_user_id,
    is_logged_in,
    login_user,
    logout_user,
    sign_up_user,
)


def render_signup(client) -> None:
    st.header("회원가입")
    st.write("Supabase Auth에 사용자를 생성하고, profiles 테이블에 닉네임을 저장합니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    with st.form("signup_form", clear_on_submit=False):
        email = st.text_input("이메일")
        password = st.text_input("비밀번호", type="password")
        nickname = st.text_input("닉네임")
        submitted = st.form_submit_button("회원가입")

    if submitted:
        ok, message = sign_up_user(client, email, password, nickname)
        if ok:
            st.success(message)
        else:
            st.error(message)


def render_login(client) -> None:
    st.header("로그인 / 로그아웃")

    if not has_supabase(client):
        show_supabase_warning()
        return

    if is_logged_in():
        st.success("현재 로그인되어 있습니다.")
        st.write(f"사용자 이메일: `{get_logged_in_email()}`")
        st.write(f"사용자 ID: `{get_logged_in_user_id()}`")

        if st.button("로그아웃"):
            logout_user(client)
            st.success("로그아웃되었습니다.")
            st.rerun()
        return

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("이메일")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")

    if submitted:
        ok, message = login_user(client, email, password)
        if ok:
            st.success(message)
            st.rerun()
        else:
            st.error(message)
