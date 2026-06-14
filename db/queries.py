from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.time_utils import now_kst


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


def fetch_table_rows(client, table_name: str, limit: int = 100) -> List[Dict[str, Any]]:
    result = client.table(table_name).select("*").limit(limit).execute()
    return result.data or []
