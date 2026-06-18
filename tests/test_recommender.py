import json
import tempfile
import unittest
from pathlib import Path


class RecommenderTest(unittest.TestCase):
    def setUp(self):
        self.routes = [
            {
                "route_id": "route_001",
                "route_name": "安静城市漫步路线",
                "tags": ["独处", "治愈", "慢走", "低预算"],
                "reason": "这条路线安静度较高，适合一个人慢慢走。",
                "spots": [
                    {
                        "name": "徐家汇书院",
                        "description": "适合阅读和独处的公共文化空间。",
                        "lat": 31.1969,
                        "lng": 121.437,
                    }
                ],
                "estimated_time": "半天",
                "budget_level": "低",
            },
            {
                "route_id": "route_002",
                "route_name": "外滩夜景初见路线",
                "tags": ["夜景", "拍照", "经典", "城市漫步"],
                "reason": "适合第一次认识上海，也适合看夜景和拍照。",
                "spots": [
                    {
                        "name": "外滩",
                        "description": "上海经典夜景与建筑群。",
                        "lat": 31.238056,
                        "lng": 121.486111,
                    }
                ],
                "estimated_time": "3-4小时",
                "budget_level": "低-中",
            },
        ]

        self.tmpdir = tempfile.TemporaryDirectory()
        self.routes_path = Path(self.tmpdir.name) / "routes.json"
        self.routes_path.write_text(json.dumps(self.routes, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_recommend_route_uses_tags_and_mood_text(self):
        from services.recommender import recommend_route

        route = recommend_route(
            selected_tags=["独处", "治愈"],
            user_text="我今天有点累，想一个人慢慢走",
            routes_path=self.routes_path,
        )

        self.assertEqual(route["route_id"], "route_001")
        self.assertEqual(route["route_name"], "安静城市漫步路线")
        self.assertIn("独处", route["matched_tags"])
        self.assertIn("治愈", route["matched_tags"])
        self.assertGreater(route["score"], 0)

    def test_recommend_route_uses_text_keywords_without_tags(self):
        from services.recommender import recommend_route

        route = recommend_route(
            selected_tags=[],
            user_text="想看夜景，适合拍照",
            routes_path=self.routes_path,
        )

        self.assertEqual(route["route_id"], "route_002")
        self.assertIn("夜景", route["matched_tags"])
        self.assertIn("拍照", route["matched_tags"])

    def test_recommend_route_returns_default_when_no_match(self):
        from services.recommender import recommend_route

        route = recommend_route(
            selected_tags=[],
            user_text="",
            routes_path=self.routes_path,
        )

        self.assertEqual(route["route_id"], "route_001")
        self.assertEqual(route["matched_tags"], [])
        self.assertEqual(route["score"], 0)

    def test_recommend_routes_keeps_compatibility_wrapper(self):
        from services.recommender import recommend_routes

        routes = recommend_routes(
            selected_tags=["独处"],
            user_text="想一个人安静散步",
            routes_path=self.routes_path,
        )

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["route_id"], "route_001")


if __name__ == "__main__":
    unittest.main()
