import unittest

from services.excel_data import load_excel_data
from services.recommender import load_routes, load_tags, recommend_route, recommend_routes


class RecommenderTest(unittest.TestCase):
    MINDSET_LABELS = ["独处", "疗愈", "灵感", "怀旧", "成长", "浪漫", "探索", "社交"]

    def test_excel_loader_uses_workbook_as_source_of_truth(self):
        data = load_excel_data()
        routes = data["routes"]
        tags = data["tags"]

        self.assertEqual(len(routes), 28)
        self.assertEqual(sum(len(route["spots"]) for route in routes), 102)
        self.assertEqual(len(tags), 15)
        self.assertEqual(data["mindset_tags"], self.MINDSET_LABELS)

        self.assertEqual([tag["user_button_text"] for tag in tags[:3]], ["一个人静静", "夜景治愈", "拍照出片"])
        self.assertEqual(tags[0]["recommended_routes"], ["R03", "R13", "R14", "R16", "R20"])

        bund_route = next(route for route in routes if route["route_id"] == "R01")
        self.assertEqual(bund_route["primary_emotion_tags"], ["想被夜景治愈", "想认识上海第一面"])
        self.assertEqual(bund_route["spots"][0]["lat"], 31.238056)
        self.assertEqual(bund_route["spots"][0]["lng"], 121.486111)
        self.assertEqual(set(bund_route["mindset_scores"]), set(self.MINDSET_LABELS))
        self.assertIn("source_note", bund_route["spots"][0])

    def test_compat_loaders_read_excel_not_static_json(self):
        self.assertEqual(len(load_routes()), 28)
        self.assertEqual(len(load_tags()), 15)

    def test_recommend_routes_returns_three_excel_candidates_with_distinct_match_percent(self):
        routes = recommend_routes(selected_tags=["疗愈"], user_text="")

        self.assertEqual(len(routes), 3)
        self.assertEqual(routes[0]["route_id"], "R26")
        self.assertIn("疗愈", routes[0]["matched_mindsets"])

        percents = [route["match_percent"] for route in routes]
        self.assertTrue(all(0 < percent < 100 for percent in percents))
        self.assertGreater(len(set(percents)), 1)
        self.assertEqual(percents, sorted(percents, reverse=True))

        excel_route_ids = {route["route_id"] for route in load_routes()}
        for route in routes:
            self.assertIn(route["route_id"], excel_route_ids)
            self.assertGreater(len(route["spots"]), 0)
            self.assertIn("match_reason", route)
            self.assertIn("suggested_card_copy", route)

    def test_selected_excel_tag_uses_mapping_priority_and_reasons(self):
        routes = recommend_routes(selected_tags=["想一个人静静"], user_text="")

        self.assertEqual([route["route_id"] for route in routes], ["R03", "R13", "R14"])
        self.assertEqual(routes[0]["route_name"], "武康路书香独处线")
        self.assertIn("想一个人静静", routes[0]["matched_tags"])
        self.assertIn("武康大楼", routes[0]["match_reason"])
        self.assertIn("文学故居", routes[0]["suggested_card_copy"])

    def test_user_text_matches_only_excel_fields(self):
        routes = recommend_routes(selected_tags=[], user_text="低噪音 慢节奏 可独处 可停留")

        self.assertEqual(routes[0]["route_id"], "R03")
        self.assertIn("想一个人静静", routes[0]["matched_tags"])

    def test_recommend_route_keeps_first_route_compatibility(self):
        route = recommend_route(selected_tags=["想被夜景治愈"], user_text="")

        self.assertEqual(route["route_id"], "R01")
        self.assertIn("想被夜景治愈", route["matched_tags"])
        self.assertIn("match_percent", route)


if __name__ == "__main__":
    unittest.main()
