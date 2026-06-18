from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from utils.time_utils import now_kst


REPORT_SELECT_COLUMNS = (
    "id, user_id, risk_type, lat, lng, description, "
    "duplicate_count, merged_group_key, created_at"
)


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


def get_user_reports_by_ids(client, report_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
    """신고 ID 목록을 한 번에 조회해 ID를 키로 하는 딕셔너리로 반환한다."""
    normalized_ids = sorted({int(report_id) for report_id in report_ids if report_id is not None})
    if not normalized_ids:
        return {}

    try:
        result = (
            client.table("user_reports")
            .select(REPORT_SELECT_COLUMNS)
            .in_("id", normalized_ids)
            .execute()
        )
        rows = result.data or []
    except Exception:
        # 일부 PostgREST/클라이언트 버전에서 in_ 필터가 다르게 동작하는 경우를 위한 안전한 대체 경로다.
        result = client.table("user_reports").select(REPORT_SELECT_COLUMNS).limit(1000).execute()
        id_set = set(normalized_ids)
        rows = [row for row in (result.data or []) if row.get("id") in id_set]

    return {int(row["id"]): row for row in rows if row.get("id") is not None}


def get_active_risk_zones_with_reports(client) -> List[Dict[str, Any]]:
    """활성 신고 위험 구역에 원본 신고 설명·시간·중복 수를 결합한다."""
    zones = get_active_risk_zones(client)
    reports = get_user_reports_by_ids(
        client,
        [zone.get("report_id") for zone in zones if zone.get("report_id") is not None],
    )

    combined: List[Dict[str, Any]] = []
    for zone in zones:
        row = dict(zone)
        report_id = row.get("report_id")
        row["report"] = reports.get(int(report_id)) if report_id is not None else None
        combined.append(row)

    return combined


def get_flood_zones(client) -> List[Dict[str, Any]]:
    result = client.table("flood_zones").select("*").execute()
    return result.data or []


def get_active_road_alerts(client) -> List[Dict[str, Any]]:
    result = client.table("road_alerts").select("*").eq("active", True).execute()
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


def fetch_table_rows(client, table_name: str, limit: int = 100) -> List[Dict[str, Any]]:
    result = client.table(table_name).select("*").limit(limit).execute()
    return result.data or []
