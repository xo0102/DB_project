from __future__ import annotations

import unittest
from typing import Any, Dict

from services.route_risk_service import (
    RouteRiskContext,
    analyze_route_risk_postgis,
    make_route_analyzer,
)
from services.spatial_service import query_route_spatial_risks, route_coordinates_to_geojson


ROUTE = [
    (37.2792, 127.9001),
    (37.2800, 127.9010),
    (37.2810, 127.9020),
]


class _Response:
    def __init__(self, data: Any):
        self.data = data


class _RpcCall:
    def __init__(self, data: Any = None, error: Exception | None = None):
        self.data = data
        self.error = error

    def execute(self) -> _Response:
        if self.error:
            raise self.error
        return _Response(self.data)


class _FakeClient:
    def __init__(self, data: Any = None, error: Exception | None = None):
        self.data = data
        self.error = error
        self.last_name = ""
        self.last_params: Dict[str, Any] = {}

    def rpc(self, name: str, params: Dict[str, Any]):
        self.last_name = name
        self.last_params = params
        return _RpcCall(self.data, self.error)


class SpatialServiceTest(unittest.TestCase):
    def test_route_geojson_uses_longitude_latitude_order(self) -> None:
        geojson = route_coordinates_to_geojson(ROUTE)
        self.assertEqual(geojson["geometry"]["type"], "LineString")
        self.assertEqual(geojson["geometry"]["coordinates"][0], [127.9001, 37.2792])

    def test_parses_postgis_polygon_intersection(self) -> None:
        client = _FakeClient(
            data=[
                {
                    "source_type": "flood_zone",
                    "source_id": 3,
                    "risk_type": "flood",
                    "title": "정문 침수 Polygon",
                    "risk_score": 30,
                    "reason": "실제 교차",
                    "latitude": 37.2800,
                    "longitude": 127.9010,
                    "distance_to_route_m": 0,
                    "influence_radius_m": 0,
                    "recent_report": False,
                    "report_description": "",
                    "report_created_at": "",
                    "duplicate_count": 0,
                    "route_position": 0.45,
                    "spatial_method": "polygon_intersection",
                    "overlap_length_m": 42.5,
                    "hazard_geojson": {
                        "type": "MultiPolygon",
                        "coordinates": [[[[127.9005, 37.2795], [127.9015, 37.2795], [127.9015, 37.2805], [127.9005, 37.2795]]]],
                    },
                }
            ]
        )

        hits = query_route_spatial_risks(client, ROUTE)

        self.assertEqual(client.last_name, "analyze_route_spatial")
        self.assertEqual(
            client.last_params["p_route_geojson"]["geometry"]["coordinates"][0],
            [127.9001, 37.2792],
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].spatial_method, "polygon_intersection")
        self.assertAlmostEqual(hits[0].overlap_length_m, 42.5)
        self.assertEqual(hits[0].hazard_geojson["type"], "MultiPolygon")

    def test_postgis_analysis_combines_weather_score(self) -> None:
        client = _FakeClient(
            data=[
                {
                    "source_type": "user_report",
                    "source_id": 10,
                    "risk_type": "flood",
                    "title": "최근 사용자 신고",
                    "risk_score": 10,
                    "reason": "신고 반경에 경로 포함",
                    "latitude": 37.2800,
                    "longitude": 127.9010,
                    "distance_to_route_m": 12.0,
                    "influence_radius_m": 50,
                    "recent_report": True,
                    "report_description": "물이 고여 있습니다.",
                    "report_created_at": "2026-06-18T09:00:00+00:00",
                    "duplicate_count": 2,
                    "route_position": 0.4,
                    "spatial_method": "report_radius",
                    "overlap_length_m": 0,
                }
            ]
        )
        context = RouteRiskContext(
            weather={
                "id": 1,
                "rain_current_mm": 5.0,
                "rain_forecast_mm": 8.0,
                "risk_score": 20,
            }
        )

        analysis = analyze_route_risk_postgis(client, ROUTE, context)

        self.assertEqual(analysis.analysis_engine, "postgis")
        self.assertEqual(analysis.total_score, 30)
        self.assertTrue(analysis.has_recent_report)
        self.assertEqual(len(analysis.items), 2)

    def test_falls_back_to_python_when_rpc_is_missing(self) -> None:
        client = _FakeClient(error=RuntimeError("PGRST202 analyze_route_spatial not found"))
        context = RouteRiskContext(
            report_zones=[
                {
                    "id": 1,
                    "report_id": 1,
                    "risk_type": "flood",
                    "center_lat": 37.2800,
                    "center_lng": 127.9010,
                    "radius_m": 100,
                    "risk_score": 10,
                    "report": {
                        "id": 1,
                        "description": "신고",
                        "duplicate_count": 1,
                    },
                }
            ]
        )
        analyzer = make_route_analyzer(client)

        analysis = analyzer(ROUTE, context)

        self.assertEqual(analysis.analysis_engine, "python_fallback")
        self.assertIn("PostGIS", analysis.analysis_warning)
        self.assertTrue(analysis.has_recent_report)


if __name__ == "__main__":
    unittest.main()
