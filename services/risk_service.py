from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import RISK_TYPE_LABELS
from db.queries import get_active_risk_zones, get_flood_zones, get_latest_weather
from utils.formatters import format_error_message, to_float, to_int
from utils.geo_utils import distance_meters
from utils.time_utils import now_kst


def calc_report_score(duplicate_count: int) -> int:
    """중복 신고 수에 따라 신고 기반 위험 점수를 계산한다."""
    if duplicate_count >= 4:
        return 20
    if duplicate_count >= 2:
        return 15
    return 10


def get_expire_time(risk_type: str):
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
