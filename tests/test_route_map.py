from __future__ import annotations

import unittest

from components.map_components import create_route_selection_map


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


if __name__ == "__main__":
    unittest.main()
