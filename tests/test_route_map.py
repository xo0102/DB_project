from __future__ import annotations

import unittest

from components.map_components import create_route_comparison_map, create_route_selection_map
from services.route_risk_service import RouteRiskAnalysis, RouteRiskItem


class RouteMapTest(unittest.TestCase):
    def test_renders_markers_and_tmap_polyline(self) -> None:
        route_map = create_route_selection_map(
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            route_coordinates=[
                (37.2792, 127.9001),
                (37.2800, 127.9010),
                (37.2822, 127.9031),
            ],
            start_name="출발",
            end_name="도착",
        )

        rendered_html = route_map.get_root().render()

        self.assertIn("TMAP 도보 경로", rendered_html)
        self.assertIn("출발", rendered_html)
        self.assertIn("도착", rendered_html)

    def test_renders_two_routes_and_report_popup(self) -> None:
        analysis = RouteRiskAnalysis(
            total_score=10,
            items=[
                RouteRiskItem(
                    source_type="user_report",
                    source_id=1,
                    risk_type="flood",
                    title="최근 사용자 신고 · 침수 위험",
                    risk_score=10,
                    reason="최근 신고 구역이 경로와 겹칩니다.",
                    latitude=37.2800,
                    longitude=127.9010,
                    influence_radius_m=50,
                    recent_report=True,
                    report_description="보행로에 물이 고였습니다.",
                    report_created_at="2026-06-18T09:00:00+00:00",
                    duplicate_count=2,
                )
            ],
            category_scores={"user_report": 10},
            has_recent_report=True,
        )

        route_map = create_route_comparison_map(
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            primary_coordinates=[
                (37.2792, 127.9001),
                (37.2800, 127.9010),
                (37.2822, 127.9031),
            ],
            alternative_coordinates=[
                (37.2792, 127.9001),
                (37.2810, 127.9005),
                (37.2822, 127.9031),
            ],
            primary_analysis=analysis,
            start_name="출발",
            end_name="도착",
        )

        rendered_html = route_map.get_root().render()
        self.assertIn("기본 TMAP 경로", rendered_html)
        self.assertIn("위험 회피 대안 경로", rendered_html)
        self.assertIn("보행로에 물이 고였습니다", rendered_html)

    def test_renders_postgis_flood_polygon(self) -> None:
        analysis = RouteRiskAnalysis(
            total_score=30,
            items=[
                RouteRiskItem(
                    source_type="flood_zone",
                    source_id=3,
                    risk_type="flood",
                    title="정문 침수 Polygon",
                    risk_score=30,
                    reason="ST_Intersects로 실제 교차했습니다.",
                    latitude=37.2800,
                    longitude=127.9010,
                    spatial_method="polygon_intersection",
                    overlap_length_m=35.2,
                    hazard_geojson={
                        "type": "MultiPolygon",
                        "coordinates": [[[[127.9005, 37.2795], [127.9015, 37.2795], [127.9015, 37.2805], [127.9005, 37.2795]]]],
                    },
                )
            ],
            category_scores={"flood_zone": 30},
            has_recent_report=False,
            analysis_engine="postgis",
        )

        route_map = create_route_comparison_map(
            start=(37.2792, 127.9001),
            end=(37.2822, 127.9031),
            primary_coordinates=[
                (37.2792, 127.9001),
                (37.2800, 127.9010),
                (37.2822, 127.9031),
            ],
            primary_analysis=analysis,
        )

        rendered_html = route_map.get_root().render()
        self.assertIn("정문 침수 Polygon", rendered_html)
        self.assertIn("실제 교차 길이", rendered_html)
        self.assertIn("MultiPolygon", rendered_html)


if __name__ == "__main__":
    unittest.main()
