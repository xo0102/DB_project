from __future__ import annotations

from typing import Optional, Tuple

import streamlit as st

from utils.formatters import format_error_message


def get_logged_in_user_id() -> Optional[str]:
    return st.session_state.get("user_id")


def get_logged_in_email() -> Optional[str]:
    return st.session_state.get("user_email")


def is_logged_in() -> bool:
    return bool(get_logged_in_user_id())


def ensure_profile(client, user_id: str, email: Optional[str] = None, nickname: Optional[str] = None) -> Tuple[bool, str]:
    """
    profiles 테이블에 사용자 프로필이 없으면 생성한다.

    RLS 정책에 따라 insert가 거절될 수 있으므로 성공/실패 메시지를 반환한다.
    """
    try:
        result = (
            client.table("profiles")
            .select("user_id, nickname")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if result.data:
            return True, "이미 프로필이 존재합니다."

        fallback_nickname = "user"
        if email and "@" in email:
            fallback_nickname = email.split("@")[0]

        profile_nickname = (nickname or fallback_nickname).strip() or fallback_nickname

        client.table("profiles").insert(
            {
                "user_id": user_id,
                "nickname": profile_nickname,
            }
        ).execute()

        return True, "profiles 테이블에 사용자 정보가 저장되었습니다."

    except Exception as e:
        return False, format_error_message(e)


def sign_up_user(client, email: str, password: str, nickname: str) -> Tuple[bool, str]:
    email = email.strip()
    nickname = nickname.strip()

    if not email or not password or not nickname:
        return False, "이메일, 비밀번호, 닉네임을 모두 입력해주세요."

    try:
        response = client.auth.sign_up(
            {
                "email": email,
                "password": password,
            }
        )

        user = getattr(response, "user", None)
        if not user:
            return False, "회원가입 응답에서 사용자 정보를 확인하지 못했습니다. Supabase 설정을 확인해주세요."

        profile_ok, profile_message = ensure_profile(client, user.id, email=email, nickname=nickname)

        if profile_ok:
            return True, "회원가입 요청이 완료되었습니다. Supabase 설정에 따라 이메일 인증이 필요할 수 있습니다."

        return True, (
            "회원가입 요청은 완료되었지만 profiles 테이블 저장은 확인이 필요합니다. "
            f"Supabase RLS 정책 또는 테이블 권한을 확인해주세요. 상세: {profile_message}"
        )

    except Exception as e:
        return False, f"회원가입 중 오류가 발생했습니다: {format_error_message(e)}"


def login_user(client, email: str, password: str) -> Tuple[bool, str]:
    email = email.strip()

    if not email or not password:
        return False, "이메일과 비밀번호를 모두 입력해주세요."

    try:
        response = client.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )

        user = getattr(response, "user", None)
        session = getattr(response, "session", None)

        if not user or not session:
            return False, "로그인 응답에서 사용자 세션을 확인하지 못했습니다. 이메일 인증 여부를 확인해주세요."

        st.session_state["user_id"] = user.id
        st.session_state["user_email"] = email
        st.session_state["access_token"] = session.access_token
        st.session_state["refresh_token"] = session.refresh_token

        try:
            client.auth.set_session(session.access_token, session.refresh_token)
        except Exception:
            pass

        ensure_profile(client, user.id, email=email)

        return True, "로그인되었습니다."

    except Exception as e:
        return False, f"로그인 중 오류가 발생했습니다: {format_error_message(e)}"


def logout_user(client) -> None:
    try:
        if client:
            client.auth.sign_out()
    except Exception:
        pass

    for key in ["user_id", "user_email", "access_token", "refresh_token"]:
        st.session_state.pop(key, None)
