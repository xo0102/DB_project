from __future__ import annotations

from datetime import timedelta, timezone

APP_TITLE = "도시 생존 네비게이터"
APP_SUBTITLE = "웹 DB 응용 · TMAP + PostGIS 위험 경로 추천"

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
    "경로 검색",
]
