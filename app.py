from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import folium
import streamlit as st
from geopy.distance import geodesic
from streamlit_folium import st_folium
from supabase import create_client


# =========================================================
# 1. 기본 설정
# =========================================================

APP_TITLE = "도시 생존 네비게이터"
APP_SUBTITLE = "웹 DB 응용 기본틀"

KST = timezone(timedelta(hours=9))
DEFAULT_LAT = 37.2792
DEFAULT_LNG = 127.9001
DEFAULT_ZOOM = 16

RISK_TYPE_LABELS = {
    "flood": "침수 위험",
    "road_control": "도로 통제",
    "other": "기타 위험",
}

DB_TABLES = [
    "profiles",
    "flood_zones",
    "road_alerts",
    "weather_snapshots",
    "user_reports",
    "report_risk_zones",
    "route_search_logs",
    "route_results",
    "route_risk_details",
]

MENU_ITEMS = [
    "홈",
    "로그인",
    "회원가입",
    "위험 지도",
    "위험 신고",
    "간단 위험도 계산",
    "DB 테이블 조회",
    "경로 검색 데모",
]


# =========================================================
# 2. 공통 유틸 함수
# =========================================================


def now_kst() -> datetime:
    """현재 시간을 KST 기준 timezone-aware datetime으로 반환한다."""
    return datetime.now(KST)


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


def get_logged_in_user_id() -> Optional[str]:
    return st.session_state.get("user_id")


def get_logged_in_email() -> Optional[str]:
    return st.session_state.get("user_email")


def is_logged_in() -> bool:
    return bool(get_logged_in_user_id())


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


def distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 위도/경도 사이의 거리를 미터 단위로 계산한다."""
    return geodesic((lat1, lng1), (lat2, lng2)).meters


def init_point_state(prefix: str, lat: float = DEFAULT_LAT, lng: float = DEFAULT_LNG) -> None:
    """지도 클릭 위치를 session_state에 초기화한다."""
    lat_key = f"{prefix}_lat"
    lng_key = f"{prefix}_lng"

    if lat_key not in st.session_state:
        st.session_state[lat_key] = lat
    if lng_key not in st.session_state:
        st.session_state[lng_key] = lng


def get_clicked_point(map_data: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float]]:
    """st_folium이 반환한 데이터에서 마지막 클릭 좌표를 추출한다."""
    if not map_data:
        return None

    clicked = map_data.get("last_clicked") or map_data.get("last_object_clicked")
    if not clicked:
        return None

    lat = clicked.get("lat")
    lng = clicked.get("lng")

    if lat is None or lng is None:
        return None

    return float(lat), float(lng)


def update_point_state_from_map(prefix: str, map_data: Optional[Dict[str, Any]]) -> None:
    """지도 클릭 좌표가 있으면 session_state에 반영하고 화면을 다시 그린다."""
    point = get_clicked_point(map_data)
    if not point:
        return

    lat, lng = point
    lat_key = f"{prefix}_lat"
    lng_key = f"{prefix}_lng"

    old_lat = st.session_state.get(lat_key)
    old_lng = st.session_state.get(lng_key)

    if old_lat != lat or old_lng != lng:
        st.session_state[lat_key] = lat
        st.session_state[lng_key] = lng
        st.rerun()


# =========================================================
# 3. 인증 관련 함수
# =========================================================


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


# =========================================================
# 4. 위험 신고 / 위험도 계산 관련 함수
# =========================================================


def calc_report_score(duplicate_count: int) -> int:
    """중복 신고 수에 따라 신고 기반 위험 점수를 계산한다."""
    if duplicate_count >= 4:
        return 20
    if duplicate_count >= 2:
        return 15
    return 10


def get_expire_time(risk_type: str) -> datetime:
    """위험 유형에 따라 신고 기반 위험 구역의 만료 시간을 정한다."""
    if risk_type == "flood":
        return now_kst() + timedelta(hours=2)
    if risk_type == "road_control":
        return now_kst() + timedelta(hours=4)
    return now_kst() + timedelta(hours=1)


def check_one_minute_limit(client, user_id: str, risk_type: str) -> bool:
    """같은 사용자가 1분 이내 같은 위험 유형을 반복 신고했는지 확인한다."""
    one_minute_ago = now_kst() - timedelta(minutes=1)

    result = (
        client.table("user_reports")
        .select("id")
        .eq("user_id", user_id)
        .eq("risk_type", risk_type)
        .gte("created_at", one_minute_ago.isoformat())
        .limit(1)
        .execute()
    )

    return bool(result.data)


def find_duplicate_report(client, risk_type: str, lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """10분 이내, 30m 이내, 동일 위험 유형 신고가 있는지 확인한다."""
    ten_minutes_ago = now_kst() - timedelta(minutes=10)

    result = (
        client.table("user_reports")
        .select("id, risk_type, lat, lng, duplicate_count")
        .eq("risk_type", risk_type)
        .gte("created_at", ten_minutes_ago.isoformat())
        .execute()
    )

    for report in result.data or []:
        old_lat = to_float(report.get("lat"))
        old_lng = to_float(report.get("lng"))
        if distance_meters(lat, lng, old_lat, old_lng) <= 30:
            return report

    return None


def create_report_and_zone(
    client,
    user_id: str,
    risk_type: str,
    lat: float,
    lng: float,
    description: str,
) -> Dict[str, Any]:
    """user_reports에 신고를 저장하고 report_risk_zones에 반경 50m 위험 구역을 생성한다."""
    report_result = client.table("user_reports").insert(
        {
            "user_id": user_id,
            "risk_type": risk_type,
            "lat": lat,
            "lng": lng,
            "description": description.strip(),
            "duplicate_count": 1,
            "merged_group_key": f"{risk_type}_{round(lat, 4)}_{round(lng, 4)}",
        }
    ).execute()

    if not report_result.data:
        raise RuntimeError("user_reports 테이블에 신고 데이터가 저장되지 않았습니다.")

    report = report_result.data[0]

    client.table("report_risk_zones").insert(
        {
            "report_id": report["id"],
            "risk_type": risk_type,
            "center_lat": lat,
            "center_lng": lng,
            "radius_m": 50,
            "risk_score": calc_report_score(1),
            "active": True,
            "expires_at": get_expire_time(risk_type).isoformat(),
        }
    ).execute()

    return report


def update_duplicate_report(client, report: Dict[str, Any]) -> Tuple[int, int]:
    """기존 신고에 중복 신고를 병합하고 위험 구역 점수와 만료 시간을 갱신한다."""
    report_id = report["id"]
    risk_type = report["risk_type"]
    new_count = to_int(report.get("duplicate_count"), 1) + 1
    new_score = calc_report_score(new_count)
    new_expires_at = get_expire_time(risk_type).isoformat()

    client.table("user_reports").update(
        {
            "duplicate_count": new_count,
        }
    ).eq("id", report_id).execute()

    zone_update = (
        client.table("report_risk_zones")
        .update(
            {
                "risk_score": new_score,
                "expires_at": new_expires_at,
                "active": True,
            }
        )
        .eq("report_id", report_id)
        .execute()
    )

    # 혹시 기존 report_risk_zones 행이 없다면 새로 생성한다.
    if not zone_update.data:
        client.table("report_risk_zones").insert(
            {
                "report_id": report_id,
                "risk_type": risk_type,
                "center_lat": to_float(report.get("lat")),
                "center_lng": to_float(report.get("lng")),
                "radius_m": 50,
                "risk_score": new_score,
                "active": True,
                "expires_at": new_expires_at,
            }
        ).execute()

    return new_count, new_score


def submit_report(
    client,
    user_id: str,
    risk_type: str,
    lat: float,
    lng: float,
    description: str,
) -> Tuple[bool, str]:
    """위험 신고 전체 흐름을 처리한다."""
    if not user_id:
        return False, "위험 신고는 로그인 후 사용할 수 있습니다."

    if risk_type not in RISK_TYPE_LABELS:
        return False, "지원하지 않는 위험 유형입니다."

    try:
        if check_one_minute_limit(client, user_id, risk_type):
            return False, "최근 1분 이내 같은 위험 유형을 이미 신고했습니다. 잠시 후 다시 시도해주세요."

        duplicate = find_duplicate_report(client, risk_type, lat, lng)

        if duplicate:
            count, score = update_duplicate_report(client, duplicate)
            return True, f"기존 신고와 병합되었습니다. 현재 누적 신고 {count}개, 반영 점수 {score}점입니다."

        create_report_and_zone(client, user_id, risk_type, lat, lng, description)
        return True, "새 위험 신고가 저장되었고, 반경 50m 위험 구역이 생성되었습니다."

    except Exception as e:
        return False, f"위험 신고 저장 중 오류가 발생했습니다: {format_error_message(e)}"


def get_active_risk_zones(client) -> List[Dict[str, Any]]:
    """현재 시점에 활성화된 신고 기반 위험 구역을 조회한다."""
    result = (
        client.table("report_risk_zones")
        .select("*")
        .eq("active", True)
        .gte("expires_at", now_kst().isoformat())
        .execute()
    )
    return result.data or []


def get_flood_zones(client) -> List[Dict[str, Any]]:
    result = client.table("flood_zones").select("*").execute()
    return result.data or []


def get_latest_weather(client) -> Optional[Dict[str, Any]]:
    result = (
        client.table("weather_snapshots")
        .select("*")
        .order("observed_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


def calculate_simple_risk(client, lat: float, lng: float) -> Tuple[int, List[str]]:
    """
    선택 위치 기준 간단 위험도 점수를 계산한다.

    이번 기본틀에서는 다음 3가지만 반영한다.
    1. 사용자 신고 기반 위험 구역
    2. 침수 이력 구역
    3. 최신 날씨 위험 점수
    """
    total_score = 0
    reasons: List[str] = []

    try:
        report_zones = get_active_risk_zones(client)
        for zone in report_zones:
            center_lat = to_float(zone.get("center_lat"))
            center_lng = to_float(zone.get("center_lng"))
            radius_m = to_int(zone.get("radius_m"), 50)
            risk_score = to_int(zone.get("risk_score"), 0)

            if distance_meters(lat, lng, center_lat, center_lng) <= radius_m:
                total_score += risk_score
                risk_label = RISK_TYPE_LABELS.get(zone.get("risk_type"), zone.get("risk_type", "위험"))
                reasons.append(f"최근 접수된 {risk_label} 신고 구역 안에 있습니다. +{risk_score}점")

    except Exception as e:
        reasons.append(f"신고 기반 위험 구역 조회 중 일부 오류가 있었습니다: {format_error_message(e)}")

    try:
        flood_zones = get_flood_zones(client)
        for zone in flood_zones:
            center_lat = to_float(zone.get("center_lat"))
            center_lng = to_float(zone.get("center_lng"))
            base_score = to_int(zone.get("base_score"), 0)
            zone_name = zone.get("zone_name", "침수 이력 구역")

            if distance_meters(lat, lng, center_lat, center_lng) <= 100:
                total_score += base_score
                reasons.append(f"'{zone_name}' 침수 이력 구역과 100m 이내입니다. +{base_score}점")

    except Exception as e:
        reasons.append(f"침수 이력 구역 조회 중 일부 오류가 있었습니다: {format_error_message(e)}")

    try:
        weather = get_latest_weather(client)
        if weather:
            weather_score = to_int(weather.get("risk_score"), 0)
            rain_current = weather.get("rain_current_mm", 0)
            rain_forecast = weather.get("rain_forecast_mm", 0)
            total_score += weather_score
            reasons.append(
                f"최신 날씨 스냅샷이 반영되었습니다. "
                f"현재 강수량 {rain_current}mm, 예보 강수량 {rain_forecast}mm, +{weather_score}점"
            )

    except Exception as e:
        reasons.append(f"날씨 데이터 조회 중 일부 오류가 있었습니다: {format_error_message(e)}")

    return min(total_score, 100), reasons


# =========================================================
# 5. 지도 관련 함수
# =========================================================


def create_base_map(lat: float, lng: float, zoom: int = DEFAULT_ZOOM) -> folium.Map:
    return folium.Map(location=[lat, lng], zoom_start=zoom, tiles="OpenStreetMap")


def add_selected_marker(m: folium.Map, lat: float, lng: float, popup: str = "선택 위치") -> None:
    folium.Marker(
        [lat, lng],
        popup=popup,
        tooltip=popup,
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(m)


def add_report_zones_to_map(m: folium.Map, zones: List[Dict[str, Any]]) -> None:
    for zone in zones:
        lat = to_float(zone.get("center_lat"))
        lng = to_float(zone.get("center_lng"))
        radius_m = to_int(zone.get("radius_m"), 50)
        risk_score = to_int(zone.get("risk_score"), 0)
        risk_type = zone.get("risk_type", "unknown")
        risk_label = RISK_TYPE_LABELS.get(risk_type, risk_type)

        folium.Circle(
            location=[lat, lng],
            radius=radius_m,
            popup=f"{risk_label} / 위험점수 {risk_score}",
            tooltip=f"{risk_label} ({risk_score}점)",
            color="red",
            fill=True,
            fill_opacity=0.25,
        ).add_to(m)


def render_folium_map(m: folium.Map, key: str, height: int = 520) -> Optional[Dict[str, Any]]:
    return st_folium(
        m,
        width=None,
        height=height,
        key=key,
    )


# =========================================================
# 6. 화면 렌더링 함수
# =========================================================


def render_sidebar() -> str:
    st.sidebar.title(APP_TITLE)
    st.sidebar.caption(APP_SUBTITLE)

    if is_logged_in():
        st.sidebar.success("로그인 상태")
        st.sidebar.caption(get_logged_in_email() or get_logged_in_user_id())
    else:
        st.sidebar.info("로그아웃 상태")

    return st.sidebar.radio("메뉴", MENU_ITEMS)


def render_home(client) -> None:
    st.header("홈")
    st.subheader("비 오는 날 야간 도보 이동을 위한 웹 DB 응용 기본틀")

    st.write(
        "이 프로젝트는 침수 위험 구역, 도로 통제 정보, 날씨 정보, 사용자 신고 데이터를 "
        "Supabase DB와 연결하여 확인하는 Streamlit 기반 웹 DB 응용 기본틀입니다."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 현재 기본틀에 포함된 기능")
        st.markdown(
            """
            - Supabase 연결 구조
            - 회원가입 / 로그인 / 로그아웃
            - 사용자 위험 신고 저장
            - 신고 기반 위험 구역 생성
            - Folium 기반 위험 지도 표시
            - 선택 위치 기준 간단 위험도 계산
            - 주요 DB 테이블 조회
            - 경로 검색 데모 화면
            """
        )

    with col2:
        st.markdown("### 추후 구현 예정 기능")
        st.markdown(
            """
            - TMAP API 기반 실제 도보 경로 탐색
            - 경로별 위험도 비교
            - 기상청 API 실시간 연동
            - 도로 통제 데이터 자동 연동
            - PostGIS 기반 공간 연산
            - 경로 LineString과 침수 Polygon 교차 판별
            """
        )

    st.markdown("### Supabase 연결 상태")
    if has_supabase(client):
        st.success("Supabase 클라이언트가 생성되었습니다. DB 조회와 입력 기능을 테스트할 수 있습니다.")
    else:
        show_supabase_warning()
        client_error = st.session_state.get("supabase_client_error")
        if client_error:
            st.caption(f"클라이언트 생성 오류: {client_error}")

    st.info(
        "이번 단계는 완성형 서비스가 아니라, DB와 웹 화면이 연결되는 흐름을 보여주는 기본틀입니다."
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


def render_risk_report(client) -> None:
    st.header("위험 신고")
    st.write("로그인한 사용자가 지도에서 위치를 선택하고 위험 정보를 신고하는 기본 화면입니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    if not is_logged_in():
        st.warning("위험 신고는 로그인 후 사용할 수 있습니다. 먼저 로그인 메뉴에서 로그인해주세요.")
        return

    init_point_state("report")

    risk_type = st.selectbox(
        "위험 유형",
        options=list(RISK_TYPE_LABELS.keys()),
        format_func=lambda key: f"{key} - {RISK_TYPE_LABELS[key]}",
    )
    description = st.text_area(
        "설명",
        placeholder="예: 보도블록 위에 물이 고여 있어서 통행이 어렵습니다.",
        height=100,
    )

    st.write("지도에서 신고 위치를 클릭하세요.")

    lat = st.session_state["report_lat"]
    lng = st.session_state["report_lng"]

    m = create_base_map(lat, lng)
    add_selected_marker(m, lat, lng, popup="신고 위치")

    try:
        zones = get_active_risk_zones(client)
        add_report_zones_to_map(m, zones)
    except Exception as e:
        st.caption(f"활성 위험 구역을 불러오지 못했습니다: {format_error_message(e)}")

    map_data = render_folium_map(m, key="report_map")
    update_point_state_from_map("report", map_data)

    st.success(f"선택된 신고 위치: {lat:.6f}, {lng:.6f}")

    if st.button("위험 신고하기", type="primary"):
        ok, message = submit_report(
            client=client,
            user_id=get_logged_in_user_id(),
            risk_type=risk_type,
            lat=lat,
            lng=lng,
            description=description,
        )
        if ok:
            st.success(message)
        else:
            st.warning(message)


def render_risk_map(client) -> None:
    st.header("위험 지도")
    st.write("report_risk_zones 테이블에 저장된 활성 위험 구역을 지도에 원 형태로 표시합니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    init_point_state("map")

    col1, col2 = st.columns(2)
    with col1:
        center_lat = st.number_input(
            "지도 중심 위도",
            value=float(st.session_state["map_lat"]),
            format="%.6f",
        )
    with col2:
        center_lng = st.number_input(
            "지도 중심 경도",
            value=float(st.session_state["map_lng"]),
            format="%.6f",
        )

    st.session_state["map_lat"] = center_lat
    st.session_state["map_lng"] = center_lng

    try:
        zones = get_active_risk_zones(client)
    except Exception as e:
        zones = []
        st.error(f"위험 구역 조회 중 오류가 발생했습니다: {format_error_message(e)}")

    m = create_base_map(center_lat, center_lng)
    add_selected_marker(m, center_lat, center_lng, popup="지도 중심")
    add_report_zones_to_map(m, zones)

    map_data = render_folium_map(m, key="risk_map")
    update_point_state_from_map("map", map_data)

    st.caption(f"현재 표시 가능한 활성 위험 구역: {len(zones)}개")

    if zones:
        with st.expander("활성 위험 구역 데이터 보기"):
            st.dataframe(zones, use_container_width=True)
    else:
        st.info("현재 표시할 활성 위험 구역이 없습니다.")


def render_simple_risk_calculator(client) -> None:
    st.header("간단 위험도 계산")
    st.write(
        "지도에서 선택한 위치를 기준으로 신고 기반 위험 구역, 침수 이력 구역, 최신 날씨 위험 점수를 단순 합산합니다."
    )

    if not has_supabase(client):
        show_supabase_warning()
        return

    init_point_state("calc")

    lat = st.session_state["calc_lat"]
    lng = st.session_state["calc_lng"]

    m = create_base_map(lat, lng)
    add_selected_marker(m, lat, lng, popup="위험도 계산 위치")

    try:
        zones = get_active_risk_zones(client)
        add_report_zones_to_map(m, zones)
    except Exception as e:
        st.caption(f"활성 위험 구역을 불러오지 못했습니다: {format_error_message(e)}")

    map_data = render_folium_map(m, key="calc_map")
    update_point_state_from_map("calc", map_data)

    st.success(f"선택된 위치: {lat:.6f}, {lng:.6f}")

    score, reasons = calculate_simple_risk(client, lat, lng)
    st.metric("위험도 점수", f"{score}/100")

    if reasons:
        st.markdown("### 계산 근거")
        for reason in reasons:
            st.write(f"- {reason}")
    else:
        st.info("현재 반영된 위험 요소가 없습니다.")


def render_db_viewer(client) -> None:
    st.header("DB 테이블 조회")
    st.write("Supabase PostgreSQL의 주요 테이블을 최대 100개 행까지 조회합니다.")

    if not has_supabase(client):
        show_supabase_warning()
        return

    table_name = st.selectbox("조회할 테이블 선택", DB_TABLES)

    if st.button("테이블 조회", type="primary"):
        try:
            result = client.table(table_name).select("*").limit(100).execute()
            data = result.data or []

            st.write(f"### `{table_name}` 테이블")
            st.write(f"조회된 행 수: {len(data)}개")

            if data:
                st.dataframe(data, use_container_width=True)
            else:
                st.info("현재 저장된 데이터가 없습니다.")

        except Exception as e:
            st.error("테이블 조회 중 오류가 발생했습니다.")
            st.caption(format_error_message(e))


def render_route_demo() -> None:
    st.header("경로 검색 데모")
    st.write(
        "이번 기본틀에서는 실제 TMAP API를 호출하지 않고, "
        "출발지/도착지 좌표 입력 화면과 추후 구현 예정 흐름만 제공합니다."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 출발지")
        start_lat = st.number_input("출발지 위도", value=DEFAULT_LAT, format="%.6f")
        start_lng = st.number_input("출발지 경도", value=DEFAULT_LNG, format="%.6f")

    with col2:
        st.markdown("### 도착지")
        end_lat = st.number_input("도착지 위도", value=DEFAULT_LAT + 0.003, format="%.6f")
        end_lng = st.number_input("도착지 경도", value=DEFAULT_LNG + 0.003, format="%.6f")

    if st.button("경로 검색 데모 확인"):
        direct_distance = distance_meters(start_lat, start_lng, end_lat, end_lng)
        st.success("입력 UI 확인이 완료되었습니다. 실제 경로 탐색은 추후 단계에서 구현합니다.")
        st.write(f"참고용 직선거리: 약 {direct_distance:.1f}m")

    st.markdown("### 추후 연결할 테이블")
    st.markdown(
        """
        - `route_search_logs`: 사용자의 경로 검색 요청 저장
        - `route_results`: 경로 후보별 거리, 시간, 총 위험 점수 저장
        - `route_risk_details`: 경로별 위험 근거 상세 저장
        """
    )

    st.info("외부 API 연동, 실제 경로 추천, PostGIS 공간 연산은 이번 단계에서는 구현하지 않습니다.")


# =========================================================
# 7. 앱 진입점
# =========================================================


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    client = get_supabase_client()

    menu = render_sidebar()

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    if menu == "홈":
        render_home(client)
    elif menu == "로그인":
        render_login(client)
    elif menu == "회원가입":
        render_signup(client)
    elif menu == "위험 지도":
        render_risk_map(client)
    elif menu == "위험 신고":
        render_risk_report(client)
    elif menu == "간단 위험도 계산":
        render_simple_risk_calculator(client)
    elif menu == "DB 테이블 조회":
        render_db_viewer(client)
    elif menu == "경로 검색 데모":
        render_route_demo()


if __name__ == "__main__":
    main()
