import json
import unittest

from services.recommender import load_routes, load_tags, recommend_route, recommend_routes


class RecommenderTest(unittest.TestCase):
    def test_selected_excel_tag_recommends_priority_route(self):
        route = recommend_route(selected_tags=["想一个人静静"], user_text="")

        self.assertEqual(route["route_id"], "R03")
        self.assertEqual(route["route_name"], "武康路书香独处线")
        self.assertIn("想一个人静静", route["matched_tags"])
        self.assertGreater(route["score"], 0)

    def test_night_healing_tag_recommends_bund_route(self):
        route = recommend_route(selected_tags=["想被夜景治愈"], user_text="")

        self.assertEqual(route["route_id"], "R01")
        self.assertEqual(route["route_name"], "外滩初见上海线")
        self.assertIn("想被夜景治愈", route["matched_tags"])

    def test_user_text_matches_excel_tag_keywords(self):
        route = recommend_route(
            selected_tags=[],
            user_text="我今天有点累，想慢慢走不赶路",
        )

        self.assertEqual(route["route_id"], "R03")
        self.assertIn("想慢慢走不赶路", route["matched_tags"])

    def test_every_excel_tag_returns_existing_route(self):
        tags = load_tags()
        route_ids = {route["route_id"] for route in load_routes()}

        self.assertEqual(len(tags), 15)
        for tag in tags:
            route = recommend_route(selected_tags=[tag["emotion_tag"]], user_text="")
            self.assertIn(route["route_id"], route_ids, tag["emotion_tag"])
            self.assertGreater(len(route["spots"]), 0)

    def test_recommend_routes_keeps_compatibility_wrapper(self):
        routes = recommend_routes(selected_tags=["想一个人静静"], user_text="")

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["route_id"], "R03")

    def test_static_data_uses_excel_tag_and_route_counts(self):
        tags = load_tags()
        routes = load_routes()

        self.assertEqual([tag["user_button_text"] for tag in tags[:3]], ["一个人静静", "夜景治愈", "拍照出片"])
        self.assertEqual(len(routes), 28)
        self.assertEqual(sum(len(route["spots"]) for route in routes), 102)

        bund_route = next(route for route in routes if route["route_id"] == "R01")
        self.assertEqual(bund_route["primary_emotion_tags"], ["想被夜景治愈", "想认识上海第一面"])
        self.assertEqual(bund_route["spots"][0]["lat"], 31.238056)
        self.assertEqual(bund_route["spots"][0]["lng"], 121.486111)

        self.assertEqual(tags[0]["recommended_routes"], ["R03", "R13", "R14", "R16", "R20"])
        self.assertIn("独处", tags[0]["backend_scene_tags"])

        tag_payload = json.dumps(tags, ensure_ascii=False)
        self.assertIn("想进入童话/动漫世界", tag_payload)


if __name__ == "__main__":
    unittest.main()
