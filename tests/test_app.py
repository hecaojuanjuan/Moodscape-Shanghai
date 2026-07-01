import unittest
from unittest.mock import patch


class AppTest(unittest.TestCase):
    def test_tags_endpoint_returns_excel_experience_and_mindset_tags(self):
        from app import app

        client = app.test_client()
        response = client.get("/api/tags")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["experience_tags"]), 15)
        self.assertEqual(data["experience_tags"][0]["emotion_tag"], "想一个人静静")
        self.assertEqual(data["experience_tags"][0]["user_button_text"], "一个人静静")
        self.assertEqual(data["mindset_tags"], ["独处", "疗愈", "灵感", "怀旧", "成长", "浪漫", "探索", "社交"])

    def test_generate_script_endpoint_returns_multiple_excel_routes(self):
        import app as app_module

        fallback_intent = {
            "summary": "低噪音 慢节奏 可独处 可停留",
            "inferred_experience_tags": [],
            "inferred_mindset_tags": [],
            "source": "fallback",
        }
        with (
            patch.object(app_module.qwen_service, "analyze_intent", return_value=fallback_intent),
            patch.object(app_module.qwen_service, "generate_route_scripts", return_value={}),
        ):
            client = app_module.app.test_client()
            response = client.post(
                "/api/generate-script",
                json={
                    "selected_tags": ["想一个人静静"],
                    "user_text": "低噪音 慢节奏 可独处 可停留",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("routes", data)
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(data["route"], data["routes"][0])
        self.assertEqual(data["script"], data["routes"][0]["script"])

        percents = [route["match_percent"] for route in data["routes"]]
        self.assertTrue(all(0 < percent < 100 for percent in percents))
        self.assertGreater(len(set(percents)), 1)

        first = data["routes"][0]
        self.assertEqual(first["route_id"], "R03")
        self.assertEqual(first["route_name"], "武康路书香独处线")
        self.assertNotIn("动态组合线", first["route_name"])
        self.assertIn("is_dynamic", first)
        self.assertIn("route_distance_km", first)
        self.assertIn("武康大楼", first["match_reason"])
        self.assertIn("武康大楼", first["script"])
        self.assertIn("情绪", first["script"])
        self.assertNotIn(first["spots"][0]["ticket_reservation"], first["script"])
        self.assertIn("script_title", first)
        self.assertNotEqual(first["script_title"], first["route_name"])
        self.assertNotIn("路线推荐", first["script_title"])
        self.assertIn("script_sections", first)
        self.assertTrue(all(section["type"] == "spot" for section in first["script_sections"]))
        self.assertEqual(len(first["script_sections"]), len(first["spots"]))
        self.assertTrue(
            any(
                section["type"] == "spot" and section["spot_name"] == "武康大楼"
                for section in first["script_sections"]
            )
        )
        self.assertNotIn("给自己留一句", first["script"])
        self.assertGreaterEqual(len(first["spots"]), 3)

        for route in data["routes"]:
            self.assertIn("match_percent", route)
            self.assertIn("matched_tags", route)
            self.assertIn("matched_mindsets", route)
            self.assertIn("match_reason", route)
            self.assertIn("suggested_card_copy", route)
            self.assertIn("script", route)
            self.assertIn("script_sections", route)
            self.assertIn("script_title", route)
            self.assertTrue(route["script_title"])
            self.assertNotEqual(route["script_title"], route["route_name"])
            self.assertNotIn("路线推荐", route["script_title"])
            self.assertEqual(len(route["script_sections"]), len(route["spots"]))
            for section in route["script_sections"]:
                self.assertEqual(section["type"], "spot")
                self.assertIn("spot_id", section)
                self.assertIn("spot_name", section)
                self.assertIn("title", section)
                self.assertIn("text", section)
                self.assertIn("paragraphs", section)
                self.assertTrue(section["paragraphs"])
                self.assertIn(section["spot_name"], section["text"])
            for spot in route["spots"]:
                self.assertIn("spot_id", spot)
                self.assertIn("name", spot)
                self.assertIn("description", spot)
                self.assertIn("open_time", spot)
                self.assertIn("ticket_reservation", spot)
            self.assertEqual(route["script_source"], "fallback")

        self.assertEqual(data["intent"], fallback_intent)

    def test_generate_script_uses_qwen_intent_and_partially_falls_back(self):
        import app as app_module

        intent = {
            "summary": "想安静地独处",
            "inferred_experience_tags": ["想一个人静静"],
            "inferred_mindset_tags": ["疗愈"],
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "analyze_intent", return_value=intent),
            patch.object(
                app_module.qwen_service,
                "generate_route_scripts",
                return_value={
                    "R03": {
                        "script": "这是一条由千问生成的真实路线文案。",
                        "script_title": "在梧桐影里慢慢静下来",
                        "script_sections": [
                            {
                                "type": "spot",
                                "spot_id": "S007",
                                "spot_name": "武康大楼",
                                "title": "第一幕｜树影先替你慢下来。",
                                "paragraphs": ["先把视线交给武康大楼。"],
                                "text": "先把视线交给武康大楼。",
                            },
                            {
                                "type": "spot",
                                "spot_id": "S008",
                                "spot_name": "徐家汇书院",
                                "title": "第二幕｜顺着阅读继续往里走。",
                                "paragraphs": ["在书院里把节奏留给自己。"],
                                "text": "在书院里把节奏留给自己。",
                            },
                            {
                                "type": "spot",
                                "spot_id": "S009",
                                "spot_name": "巴金故居",
                                "title": "第三幕｜把安静带回今天。",
                                "paragraphs": ["最后把这段安静带回今天。"],
                                "text": "最后把这段安静带回今天。",
                            },
                        ],
                    }
                },
            ),
        ):
            client = app_module.app.test_client()
            response = client.post(
                "/api/generate-script",
                json={
                    "selected_tags": [],
                    "user_text": "今天有点累，想安静地慢慢走",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["intent"], intent)
        self.assertEqual(data["routes"][0]["route_id"], "R03")
        self.assertEqual(data["routes"][0]["script"], "这是一条由千问生成的真实路线文案。")
        self.assertEqual(data["routes"][0]["script_title"], "在梧桐影里慢慢静下来")
        self.assertEqual(data["routes"][0]["script_sections"][0]["spot_name"], "武康大楼")
        self.assertEqual(data["routes"][0]["script_sections"][0]["paragraphs"][0], "先把视线交给武康大楼。")
        self.assertEqual(data["routes"][0]["script_source"], "qwen")
        self.assertTrue(
            all(route["script_source"] == "fallback" for route in data["routes"][1:])
        )
        self.assertTrue(
            all(route["script_sections"] for route in data["routes"][1:])
        )

    def test_qwen_intent_can_drive_ranking_without_changing_route_data(self):
        import app as app_module

        intent = {
            "summary": "想去看上海夜景",
            "inferred_experience_tags": ["想被夜景治愈"],
            "inferred_mindset_tags": ["浪漫"],
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "analyze_intent", return_value=intent),
            patch.object(app_module.qwen_service, "generate_route_scripts", return_value={}),
        ):
            client = app_module.app.test_client()
            response = client.post(
                "/api/generate-script",
                json={
                    "selected_tags": [],
                    "user_text": "请理解我此刻想去看城市灯光",
                },
            )

        data = response.get_json()
        self.assertEqual(data["routes"][0]["route_id"], "R01")
        self.assertEqual(data["routes"][0]["spots"][0]["name"], "外滩")
        self.assertEqual(data["routes"][0]["script_source"], "fallback")
        self.assertTrue(data["routes"][0]["script_title"])
        self.assertTrue(all(section["type"] == "spot" for section in data["routes"][0]["script_sections"]))
        self.assertTrue(data["routes"][0]["script_sections"][0]["paragraphs"])
        self.assertIn("外滩", data["routes"][0]["script_sections"][0]["text"])

    def test_generate_script_endpoint_requires_current_input_before_profile_enhancement(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/generate-script",
            json={
                "selected_tags": [],
                "user_text": "",
                "profile_answers": {
                    "pace": "slow_stop",
                    "healing_space": "quiet_street",
                    "shanghai_style": "old_shanghai",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["needs_input"])
        self.assertEqual(data["routes"], [])
        self.assertEqual(data["message"], "请在左侧选择标签，或者写入你的心情状态。")
        self.assertEqual(data["script"], "")
        self.assertEqual(data["script_sections"], [])

    def test_recommend_routes_endpoint_returns_multiple_routes(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/recommend-routes",
            json={
                "selected_tags": ["疗愈"],
                "user_text": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(data["routes"][0]["route_id"], "R26")
        self.assertEqual(data["routes"][0]["route_name"], "松江郊野文化疗愈线")
        self.assertNotIn("动态组合线", data["routes"][0]["route_name"])
        self.assertIn("疗愈", data["routes"][0]["matched_mindsets"])

    def test_recommend_routes_endpoint_includes_profile_similarity_when_profile_is_valid(self):
        from app import app

        client = app.test_client()
        response = client.post(
            "/api/recommend-routes",
            json={
                "selected_tags": ["想一个人静静"],
                "user_text": "",
                "profile_answers": {
                    "pace": "slow_stop",
                    "healing_space": "quiet_street",
                    "shanghai_style": "old_shanghai",
                    "companion": "solo",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["needs_input"])
        self.assertGreater(data["routes"][0]["profile_similarity"], 0)
        self.assertIn("安静", data["routes"][0]["matched_profile_traits"])


if __name__ == "__main__":
    unittest.main()
