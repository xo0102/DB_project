from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from components.map_components import (
    create_route_comparison_map,
    create_route_selection_map,
    render_folium_map,
)
from config import DEFAULT_LAT, DEFAULT_LNG, KST
from db.client import has_supabase
from services.route_risk_service import (
    RISK_TRIGGER_SCORE,
    RouteRecommendation,
    RouteRiskAnalysis,
    RouteRiskItem,
    create_route_recommendation,
    load_route_risk_context,
)
from services.tmap_service import PedestrianRoute, TmapApiError, search_pedestrian_route
from utils.geo_utils import distance_meters
from utils.secret_utils import read_secret
from utils.state_utils import get_clicked_point

SESSION_RECOMMENDATION_KEY = "route_recommendation_result"
DIRECT_DISTANCE_KEY = "tmap_direct_distance"
START_LAT_KEY = "route_start_lat"
START_LNG_KEY = "route_start_lng"
END_LAT_KEY = "route_end_lat"
END_LNG_KEY = "route_end_lng"
START_NAME_KEY = "route_start_name"
END_NAME_KEY = "route_end_name"
SELECT_TARGET_KEY = "route_select_target"
SELECT_TARGET_WIDGET_KEY = "route_select_target_widget"
LAST_CLICK_KEY = "route_last_processed_click"
MAP_VERSION_KEY = "route_map_version"
FLASH_MESSAGE_KEY = "route_flash_message"

DEFAULT_END_LAT = DEFAULT_LAT + 0.003
DEFAULT_END_LNG = DEFAULT_LNG + 0.003

SOURCE_LABELS = {
    "user_report": "최근 사용자 신고",
    "flood_zone": "침수 이력·예상 구역",
    "road_alert": "도로 통제·알림",
    "weather": "날씨",
}


def _format_distance(distance_m: int) -> str:
    if distance_m >= 1000:
        return f"{distance_m / 1000:.2f} km"
    return f"{distance_m:,} m"


def _format_duration(duration_sec: int) -> str:
    if duration_sec <= 0:
        return "정보 없음"

    minutes = max(1, round(duration_sec / 60))
    hours, remain_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {remain_minutes}분"
    return f"약 {minutes}분"


def _format_datetime(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(KST)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _init_route_state() -> None:
    defaults: Dict[str, Any] = {
        START_LAT_KEY: DEFAULT_LAT,
        START_LNG_KEY: DEFAULT_LNG,
        END_LAT_KEY: DEFAULT_END_LAT,
        END_LNG_KEY: DEFAULT_END_LNG,
        START_NAME_KEY: "연세대학교 미래캠퍼스",
        END_NAME_KEY: "도착지",
        SELECT_TARGET_KEY: "출발지",
        SELECT_TARGET_WIDGET_KEY: "출발지",
        MAP_VERSION_KEY: 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_route_result() -> None:
    st.session_state.pop(SESSION_RECOMMENDATION_KEY, None)
    st.session_state.pop(DIRECT_DISTANCE_KEY, None)


def _sync_select_target_from_widget() -> None:
    st.session_state[SELECT_TARGET_KEY] = st.session_state.get(
        SELECT_TARGET_WIDGET_KEY,
        "출발지",
    )


def _refresh_map_component() -> None:
    st.session_state[MAP_VERSION_KEY] = int(st.session_state.get(MAP_VERSION_KEY, 0)) + 1
    st.session_state.pop(LAST_CLICK_KEY, None)


def _swap_points() -> None:
    start_lat = st.session_state[START_LAT_KEY]
    start_lng = st.session_state[START_LNG_KEY]
    start_name = st.session_state[START_NAME_KEY]

    st.session_state[START_LAT_KEY] = st.session_state[END_LAT_KEY]
    st.session_state[START_LNG_KEY] = st.session_state[END_LNG_KEY]
    st.session_state[START_NAME_KEY] = st.session_state[END_NAME_KEY]

    st.session_state[END_LAT_KEY] = start_lat
    st.session_state[END_LNG_KEY] = start_lng
    st.session_state[END_NAME_KEY] = start_name

    _clear_route_result()
    _refresh_map_component()


def _reset_points() -> None:
    st.session_state[START_LAT_KEY] = DEFAULT_LAT
    st.session_state[START_LNG_KEY] = DEFAULT_LNG
    st.session_state[END_LAT_KEY] = DEFAULT_END_LAT
    st.session_state[END_LNG_KEY] = DEFAULT_END_LNG
    st.session_state[START_NAME_KEY] = "연세대학교 미래캠퍼스"
    st.session_state[END_NAME_KEY] = "도착지"
    st.session_state[SELECT_TARGET_KEY] = "출발지"
    st.session_state[SELECT_TARGET_WIDGET_KEY] = "출발지"

    _clear_route_result()
    _refresh_map_component()


def _prepare_new_selection() -> None:
    _clear_route_result()
    st.session_state[FLASH_MESSAGE_KEY] = "경로 결과를 지웠습니다. 지도에서 새 지점을 선택하세요."
    _refresh_map_component()


def _point_signature(point: Tuple[float, float]) -> str:
    return f"{point[0]:.7f},{point[1]:.7f}"


def _process_map_click(map_data: Optional[Dict[str, Any]]) -> None:
    """새 지도 클릭을 현재 선택 모드의 출발지 또는 도착지에 반영한다."""
    point = get_clicked_point(map_data)
    if point is None:
        return

    signature = _point_signature(point)
    if st.session_state.get(LAST_CLICK_KEY) == signature:
        return

    st.session_state[LAST_CLICK_KEY] = signature
    lat, lng = point

    if st.session_state[SELECT_TARGET_KEY] == "출발지":
        st.session_state[START_LAT_KEY] = lat
        st.session_state[START_LNG_KEY] = lng
        st.session_state[SELECT_TARGET_KEY] = "도착지"
        st.session_state[FLASH_MESSAGE_KEY] = "출발지를 설정했습니다. 이제 지도에서 도착지를 선택하세요."
    else:
        st.session_state[END_LAT_KEY] = lat
        st.session_state[END_LNG_KEY] = lng
        st.session_state[FLASH_MESSAGE_KEY] = "도착지를 설정했습니다. 경로 검색 버튼을 눌러주세요."

    _clear_route_result()
    _refresh_map_component()
    st.rerun()


def _show_point_summary() -> None:
    start_lat = float(st.session_state[START_LAT_KEY])
    start_lng = float(st.session_state[START_LNG_KEY])
    end_lat = float(st.session_state[END_LAT_KEY])
    end_lng = float(st.session_state[END_LNG_KEY])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🟢 출발지")
        st.code(f"위도 {start_lat:.7f}\n경도 {start_lng:.7f}", language="text")

    with col2:
        st.markdown("#### 🔴 도착지")
        st.code(f"위도 {end_lat:.7f}\n경도 {end_lng:.7f}", language="text")


def _search_route(app_key: str, client) -> None:
    start = (
        float(st.session_state[START_LAT_KEY]),
        float(st.session_state[START_LNG_KEY]),
    )
    end = (
        float(st.session_state[END_LAT_KEY]),
        float(st.session_state[END_LNG_KEY]),
    )
    start_name = str(st.session_state[START_NAME_KEY])
    end_name = str(st.session_state[END_NAME_KEY])

    try:
        with st.spinner("TMAP 기본 보행 경로를 검색하고 있습니다..."):
            primary_route = search_pedestrian_route(
                app_key=app_key,
                start_lat=start[0],
                start_lng=start[1],
                end_lat=end[0],
                end_lng=end[1],
                start_name=start_name,
                end_name=end_name,
            )

        if has_supabase(client):
            with st.spinner(
                "침수·도로 통제·최근 신고 위험을 분석하고, 필요하면 회피 경로를 탐색하고 있습니다..."
            ):
                context = load_route_risk_context(client)
                recommendation = create_route_recommendation(
                    primary_route=primary_route,
                    context=context,
                    app_key=app_key,
                    start=start,
                    end=end,
                    start_name=start_name,
                    end_name=end_name,
                )
        else:
            recommendation = RouteRecommendation(
                primary_route=primary_route,
                primary_analysis=None,
                risk_context_warnings=["Supabase에 연결되지 않아 경로 위험 분석을 생략했습니다."],
            )

        st.session_state[SESSION_RECOMMENDATION_KEY] = recommendation
        st.session_state[DIRECT_DISTANCE_KEY] = distance_meters(
            start[0],
            start[1],
            end[0],
            end[1],
        )

        if recommendation.alternative_route:
            st.session_state[FLASH_MESSAGE_KEY] = (
                "기본 경로 분석을 마쳤고, 위험 회피 대안 경로도 함께 생성했습니다."
            )
        else:
            st.session_state[FLASH_MESSAGE_KEY] = "기본 경로 검색과 위험 분석을 완료했습니다."

        _refresh_map_component()
        st.rerun()

    except TmapApiError as error:
        _clear_route_result()
        st.error(str(error))
    except Exception as error:
        _clear_route_result()
        st.error(f"예상하지 못한 오류가 발생했습니다: {error}")


def _risk_rows(analysis: RouteRiskAnalysis) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in analysis.items:
        if item.distance_to_route_m is None:
            distance_text = "전체 경로 공통"
        else:
            distance_text = f"약 {item.distance_to_route_m:.1f}m"

        detail = item.report_description if item.recent_report else item.reason
        rows.append(
            {
                "출처": SOURCE_LABELS.get(item.source_type, item.source_type),
                "위험 정보": item.title,
                "점수": item.risk_score,
                "경로와 거리": distance_text,
                "상세/신고 내용": detail,
                "신고 시각": _format_datetime(item.report_created_at) if item.recent_report else "-",
                "누적 신고": item.duplicate_count if item.recent_report else "-",
            }
        )
    return rows


def _show_risk_details(title: str, analysis: Optional[RouteRiskAnalysis]) -> None:
    with st.expander(title, expanded=bool(analysis and analysis.items)):
        if not analysis:
            st.info("Supabase 위험 데이터를 불러오지 못해 상세 분석이 없습니다.")
            return

        if not analysis.items:
            st.success("이 경로에 반영된 위험 요소가 없습니다.")
            return

        st.dataframe(_risk_rows(analysis), use_container_width=True, hide_index=True)

        report_items = [item for item in analysis.items if item.recent_report]
        if report_items:
            st.markdown("#### 포함된 최근 신고")
            for item in report_items:
                st.warning(
                    f"**{item.title}** · {item.risk_score}점  \n"
                    f"신고 내용: {item.report_description or '설명 없음'}  \n"
                    f"신고 시각: {_format_datetime(item.report_created_at)} · 누적 {item.duplicate_count}건"
                )


def _show_route_card(
    *,
    title: str,
    route: PedestrianRoute,
    analysis: Optional[RouteRiskAnalysis],
    badge: str,
) -> None:
    with st.container(border=True):
        st.markdown(f"### {title}")
        st.caption(badge)

        metric_col1, metric_col2 = st.columns(2)
        metric_col1.metric("거리", _format_distance(route.distance_m))
        metric_col2.metric("예상 시간", _format_duration(route.duration_sec))

        if analysis:
            risk_col1, risk_col2 = st.columns(2)
            risk_col1.metric("총 위험도", f"{analysis.total_score}/100")
            risk_col2.metric("최근 신고", f"{analysis.recent_report_count}건")

            if analysis.has_recent_report:
                st.error("이 경로에는 현재 활성 상태인 최근 사용자 신고가 포함됩니다.")
            elif analysis.total_score >= RISK_TRIGGER_SCORE:
                st.warning(f"위험도가 기준점수 {RISK_TRIGGER_SCORE}점 이상입니다.")
            else:
                st.success("최근 신고가 없고 위험도가 기준점수보다 낮습니다.")
        else:
            st.info("DB 위험 분석 없이 TMAP 경로 정보만 표시합니다.")


def _show_route_guides(
    primary_route: PedestrianRoute,
    alternative_route: Optional[PedestrianRoute],
) -> None:
    tabs = st.tabs(
        ["기본 경로 길 안내"]
        + (["위험 회피 경로 길 안내"] if alternative_route else [])
    )

    with tabs[0]:
        if primary_route.guide_points:
            st.dataframe(primary_route.guide_points, use_container_width=True, hide_index=True)
        else:
            st.info("별도의 안내 지점이 반환되지 않았습니다.")

    if alternative_route:
        with tabs[1]:
            if alternative_route.guide_points:
                st.dataframe(alternative_route.guide_points, use_container_width=True, hide_index=True)
            else:
                st.info("별도의 안내 지점이 반환되지 않았습니다.")


def _show_recommendation(result: RouteRecommendation, direct_distance: float) -> None:
    st.markdown("### 경로 추천 결과")
    primary_analysis = result.primary_analysis
    alternative_analysis = result.alternative_analysis

    if result.risk_context_warnings:
        with st.expander("위험 데이터 조회 참고사항"):
            for warning in result.risk_context_warnings:
                st.warning(warning)

    if primary_analysis is None:
        st.info("TMAP 경로는 정상 수신했지만 Supabase 위험 분석은 수행하지 못했습니다.")
    elif not primary_analysis.should_offer_alternative:
        st.success(
            f"기본 경로의 위험도는 {primary_analysis.total_score}/100이고 최근 신고가 없어, "
            "별도의 우회 경로를 만들지 않았습니다."
        )
    elif result.alternative_route and result.alternative_fully_avoids_trigger:
        st.success(
            "기본 경로에 높은 위험 또는 최근 신고가 감지되어, "
            "최근 신고를 포함하지 않고 위험도 50점 미만인 대안 경로를 찾았습니다."
        )
    elif result.alternative_route and result.alternative_improves_risk:
        st.warning(
            "완전히 모든 위험을 제거하지는 못했지만, 기본 경로보다 위험도가 낮은 대안 경로를 찾았습니다."
        )
    elif result.alternative_route:
        st.warning(
            "대안 경로를 생성했지만 현재 데이터 기준으로 기본 경로보다 확실히 안전하다고 판단하기 어렵습니다. "
            "두 경로의 상세 위험 정보를 비교해주세요."
        )
    else:
        st.error(result.alternative_error or "위험 회피 대안 경로를 생성하지 못했습니다.")

    card_columns = st.columns(2 if result.alternative_route else 1)
    with card_columns[0]:
        _show_route_card(
            title="기본 TMAP 경로",
            route=result.primary_route,
            analysis=primary_analysis,
            badge="위험 분석 전의 기본 보행 경로",
        )

    if result.alternative_route:
        with card_columns[1]:
            badge = (
                "추천 경로 · 최근 신고 및 고위험 구간 회피 성공"
                if result.alternative_fully_avoids_trigger
                else "위험 회피를 시도한 대안 경로"
            )
            _show_route_card(
                title="위험 회피 대안 경로",
                route=result.alternative_route,
                analysis=alternative_analysis,
                badge=badge,
            )

    st.caption(f"참고용 출발지-도착지 직선거리: 약 {direct_distance:,.1f}m")
    if result.alternative_attempts:
        st.caption(f"대안 경로 탐색을 위해 TMAP 후보 {result.alternative_attempts}개를 비교했습니다.")

    detail_col1, detail_col2 = st.columns(2 if result.alternative_route else 1)
    with detail_col1:
        _show_risk_details("기본 경로의 위험·신고 상세", primary_analysis)
    if result.alternative_route:
        with detail_col2:
            _show_risk_details("대안 경로의 위험·신고 상세", alternative_analysis)

    st.markdown("### 경로별 길 안내")
    _show_route_guides(result.primary_route, result.alternative_route)

    with st.expander("개발 확인용 결과 요약"):
        st.json(
            {
                "primary": {
                    "distance_m": result.primary_route.distance_m,
                    "duration_sec": result.primary_route.duration_sec,
                    "risk_score": primary_analysis.total_score if primary_analysis else None,
                    "recent_reports": primary_analysis.recent_report_count if primary_analysis else None,
                },
                "alternative": (
                    {
                        "distance_m": result.alternative_route.distance_m,
                        "duration_sec": result.alternative_route.duration_sec,
                        "risk_score": alternative_analysis.total_score if alternative_analysis else None,
                        "recent_reports": alternative_analysis.recent_report_count if alternative_analysis else None,
                        "pass_points": result.alternative_pass_points,
                    }
                    if result.alternative_route
                    else None
                ),
            }
        )


def render_route_search(client) -> None:
    _init_route_state()

    st.header("위험 기반 TMAP 도보 경로 추천")
    st.write(
        "지도에서 출발지와 도착지를 선택하면 TMAP 기본 경로를 조회한 뒤, "
        "Supabase의 침수 구역·도로 통제·최근 사용자 신고를 반영해 위험도를 계산합니다."
    )
    st.info(
        f"기본 경로 위험도가 {RISK_TRIGGER_SCORE}점 이상이거나 최근 신고가 포함되면, "
        "위험을 우회하도록 경유점을 생성해 대안 경로를 추가 탐색합니다."
    )

    flash_message = st.session_state.pop(FLASH_MESSAGE_KEY, None)
    if flash_message:
        st.success(flash_message)

    app_key = read_secret("TMAP_APP_KEY")
    if not app_key:
        st.warning(
            "TMAP appKey가 설정되지 않았습니다. "
            "`.streamlit/secrets.toml`에 `TMAP_APP_KEY` 값을 추가한 뒤 앱을 다시 실행해주세요."
        )

    if not has_supabase(client):
        st.warning("Supabase 연결이 없어 위험 분석은 생략되고 TMAP 기본 경로만 표시됩니다.")

    with st.expander("지점 이름 설정", expanded=False):
        name_col1, name_col2 = st.columns(2)
        with name_col1:
            st.text_input("출발지 이름", key=START_NAME_KEY)
        with name_col2:
            st.text_input("도착지 이름", key=END_NAME_KEY)

    st.markdown("### 1. 지도에서 지점 선택")
    st.session_state[SELECT_TARGET_WIDGET_KEY] = st.session_state[SELECT_TARGET_KEY]
    st.radio(
        "현재 지도 클릭으로 설정할 지점",
        options=["출발지", "도착지"],
        horizontal=True,
        key=SELECT_TARGET_WIDGET_KEY,
        on_change=_sync_select_target_from_widget,
        help="출발지를 선택하면 자동으로 도착지 선택 모드로 넘어갑니다.",
    )

    action_col1, action_col2, action_col3 = st.columns([1, 1, 3])
    with action_col1:
        st.button("출발·도착 바꾸기", on_click=_swap_points, use_container_width=True)
    with action_col2:
        st.button("초기화", on_click=_reset_points, use_container_width=True)
    with action_col3:
        current_target = st.session_state[SELECT_TARGET_KEY]
        st.info(f"현재 선택 모드: **{current_target}** — 아래 지도에서 원하는 위치를 클릭하세요.")

    _show_point_summary()

    stored_result: Optional[RouteRecommendation] = st.session_state.get(SESSION_RECOMMENDATION_KEY)
    start = (
        float(st.session_state[START_LAT_KEY]),
        float(st.session_state[START_LNG_KEY]),
    )
    end = (
        float(st.session_state[END_LAT_KEY]),
        float(st.session_state[END_LNG_KEY]),
    )

    if stored_result:
        route_map = create_route_comparison_map(
            start=start,
            end=end,
            primary_coordinates=stored_result.primary_route.route_coordinates,
            alternative_coordinates=(
                stored_result.alternative_route.route_coordinates
                if stored_result.alternative_route
                else None
            ),
            primary_analysis=stored_result.primary_analysis,
            alternative_analysis=stored_result.alternative_analysis,
            start_name=str(st.session_state[START_NAME_KEY]),
            end_name=str(st.session_state[END_NAME_KEY]),
        )
        map_key = f"route_result_map_{st.session_state[MAP_VERSION_KEY]}"
        render_folium_map(route_map, key=map_key, height=650, returned_objects=[])
        st.caption(
            "기본 경로는 위험 감지 시 빨간색, 위험 회피 대안은 초록색으로 표시됩니다. "
            "위험 마커를 눌러 신고 내용과 위험 근거를 확인할 수 있습니다."
        )
        st.button(
            "경로 결과 지우고 새 지점 선택",
            on_click=_prepare_new_selection,
            use_container_width=True,
        )
    else:
        route_map = create_route_selection_map(
            start=start,
            end=end,
            route_coordinates=None,
            start_name=str(st.session_state[START_NAME_KEY]),
            end_name=str(st.session_state[END_NAME_KEY]),
        )
        map_key = f"route_selection_map_{st.session_state[MAP_VERSION_KEY]}"
        map_data = render_folium_map(
            route_map,
            key=map_key,
            height=620,
            returned_objects=["last_clicked"],
        )
        _process_map_click(map_data)
        st.caption("초록 마커는 출발지, 빨간 마커는 도착지입니다.")

    st.markdown("### 2. 실제 경로 검색 및 위험 분석")
    search_disabled = not bool(app_key)
    if st.button(
        "경로 검색하고 위험 회피 대안 비교",
        type="primary",
        disabled=search_disabled,
        use_container_width=True,
    ):
        if not app_key:
            st.error("TMAP_APP_KEY를 먼저 설정해주세요.")
        else:
            _search_route(app_key, client)

    if stored_result:
        direct_distance = float(st.session_state.get(DIRECT_DISTANCE_KEY, 0.0))
        _show_recommendation(stored_result, direct_distance)

    st.caption(
        "현재 단계는 중심 좌표·반경 기반 근사 분석이며 검색 결과를 DB에 저장하지 않습니다. "
        "다음 단계에서 route_results 저장과 PostGIS의 정확한 공간 교차 판별을 연결합니다."
    )
