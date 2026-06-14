from __future__ import annotations

from geopy.distance import geodesic


def distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 위도/경도 사이의 거리를 미터 단위로 계산한다."""
    return geodesic((lat1, lng1), (lat2, lng2)).meters
