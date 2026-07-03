import json
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

        intent = {
            "normalized_intent": "低噪音 慢节奏 可独处 可停留",
            "summary": "低噪音 慢节奏 可独处 可停留",
            "inferred_experience_tags": [],
            "inferred_mindset_tags": [],
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent),
            patch.object(app_module.qwen_service, "generate_route_scripts", side_effect=_qwen_scripts_for_routes),
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
            self.assertEqual(route["script_source"], "qwen")

        self.assertEqual(data["intent"], intent)

    def test_generate_script_retries_missing_routes_when_qwen_omits_any_route_script(self):
        import app as app_module

        intent = {
            "normalized_intent": "想安静地独处",
            "summary": "想安静地独处",
            "inferred_experience_tags": ["想一个人静静"],
            "inferred_mindset_tags": ["疗愈"],
            "source": "qwen",
        }
        script_generator = _first_call_first_route_then_all_remaining()
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent),
            patch.object(
                app_module.qwen_service,
                "generate_route_scripts",
                side_effect=script_generator,
            ) as generate_scripts,
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
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(generate_scripts.call_count, 2)
        retry_routes = generate_scripts.call_args_list[1].args[0]
        self.assertEqual(
            [route["route_id"] for route in retry_routes],
            [route["route_id"] for route in data["routes"][1:]],
        )
        self.assertEqual(data["route"], data["routes"][0])
        self.assertEqual(data["script"], data["routes"][0]["script"])
        self.assertEqual(data["script_source"], "qwen")
        self.assertIn("来自千问", data["script_source_message"])

        for route in data["routes"]:
            self.assertEqual(route["script_source"], "qwen")
            self.assertIn("来自千问", route["script_source_message"])
            self.assertIn("这是一条由千问生成的真实路线文案", route["script"])
            self.assertEqual(route["script_title"], f"{route['route_name']}的千问剧本")
            self.assertEqual(len(route["script_sections"]), len(route["spots"]))
            for section, spot in zip(route["script_sections"], route["spots"]):
                self.assertEqual(section["type"], "spot")
                self.assertEqual(section["spot_id"], spot["spot_id"])
                self.assertEqual(section["spot_name"], spot["name"])
                self.assertIn("paragraphs", section)
                self.assertTrue(section["paragraphs"])
        self.assertNotIn("本地模板", json.dumps(data, ensure_ascii=False))

    def test_generate_script_marks_routes_missing_when_retry_still_omits_scripts(self):
        import app as app_module

        intent = {
            "normalized_intent": "想安静地独处",
            "summary": "想安静地独处",
            "inferred_experience_tags": ["想一个人静静"],
            "inferred_mindset_tags": ["疗愈"],
            "source": "qwen",
        }
        script_generator = _first_call_first_route_then_empty_retry()
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent),
            patch.object(
                app_module.qwen_service,
                "generate_route_scripts",
                side_effect=script_generator,
            ) as generate_scripts,
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
        self.assertEqual(generate_scripts.call_count, 2)
        self.assertEqual(data["routes"][0]["script_source"], "qwen")
        self.assertEqual(data["routes"][1]["script_source"], "qwen_missing")
        self.assertEqual(data["routes"][2]["script_source"], "qwen_missing")
        for route in data["routes"][1:]:
            self.assertEqual(route["script"], "")
            self.assertEqual(route["script_title"], "")
            self.assertEqual(route["script_sections"], [])
            self.assertIn("千问未返回该路线剧本，请重试", route["script_source_message"])
        self.assertNotIn("本地模板", json.dumps(data, ensure_ascii=False))

    def test_qwen_intent_can_drive_ranking_without_changing_route_data(self):
        import app as app_module

        intent = {
            "normalized_intent": "想去看上海夜景",
            "summary": "想去看上海夜景",
            "inferred_experience_tags": ["想被夜景治愈"],
            "inferred_mindset_tags": ["浪漫"],
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent),
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

        self.assertEqual(response.status_code, 502)
        data = response.get_json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(data["intent"], intent)
        self.assertTrue(all(route["script_source"] == "qwen_missing" for route in data["routes"]))
        self.assertIn("千问未返回路线剧本，请重试", data["script_source_message"])
        self.assertIn("千问未返回路线剧本，请重试", data["message"])
        self.assertNotIn("本地模板", json.dumps(data, ensure_ascii=False))

    def test_generate_script_returns_error_when_qwen_is_not_configured(self):
        import app as app_module

        with patch.object(app_module.qwen_service, "api_key", ""):
            client = app_module.app.test_client()
            response = client.post(
                "/api/generate-script",
                json={
                    "selected_tags": ["想一个人静静"],
                    "user_text": "想安静地慢慢走",
                },
            )

        self.assertEqual(response.status_code, 502)
        data = response.get_json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(data["script_source"], "qwen_missing")
        self.assertEqual(data["error_code"], "qwen_not_configured")
        self.assertIn("千问未配置", data["script_source_message"])
        self.assertTrue(all(route["script_source"] == "qwen_missing" for route in data["routes"]))
        self.assertNotIn("本地模板", json.dumps(data, ensure_ascii=False))

    def test_generate_script_returns_error_when_qwen_request_fails(self):
        import app as app_module

        intent = {
            "normalized_intent": "想慢慢走",
            "summary": "想慢慢走",
            "inferred_experience_tags": [],
            "inferred_mindset_tags": [],
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent),
            patch.object(app_module.qwen_service, "generate_route_scripts", side_effect=TimeoutError("timed out")),
        ):
            client = app_module.app.test_client()
            response = client.post(
                "/api/generate-script",
                json={
                    "selected_tags": ["想一个人静静"],
                    "user_text": "想慢慢走",
                },
            )

        self.assertEqual(response.status_code, 502)
        data = response.get_json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertTrue(all(route["script_source"] == "qwen_missing" for route in data["routes"]))
        self.assertIn("千问调用失败", data["script_source_message"])
        self.assertIn("千问调用失败", data["message"])
        self.assertNotIn("本地模板", json.dumps(data, ensure_ascii=False))

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

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(data["needs_input"])
        self.assertEqual(data["routes"], [])
        self.assertEqual(data["error"], "请选择标签或输入心情描述")
        self.assertEqual(data["message"], "请选择标签或输入心情描述")
        self.assertEqual(data["script"], "")
        self.assertEqual(data["script_sections"], [])

    def test_generate_script_accepts_mood_text_alias_without_selected_tags(self):
        import app as app_module

        intent = {
            "normalized_intent": "想找二次元周边",
            "summary": "想找二次元周边",
            "inferred_tags": ["想进入童话/动漫世界"],
            "inferred_experience_tags": ["想进入童话/动漫世界"],
            "inferred_mindset_tags": [],
            "preferred_scene_types": ["二次元", "IP周边"],
            "avoid_scene_types": [],
            "must_have": ["周边"],
            "soft_preferences": [],
            "route_keywords": ["二次元", "周边"],
            "mood_tone": "想探索",
            "budget_preference": "unknown",
            "crowd_preference": "balanced",
            "time_preference": "flexible",
            "confidence": 0.9,
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent) as parse_intent,
            patch.object(app_module.qwen_service, "generate_route_scripts", side_effect=_qwen_scripts_for_routes),
        ):
            client = app_module.app.test_client()
            response = client.post(
                "/api/generate-script",
                json={
                    "tags": [],
                    "mood_text": "想找二次元周边",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["intent"], intent)
        self.assertEqual(data["routes"][0]["route_id"], "R30")
        parse_intent.assert_called_once()
        self.assertEqual(parse_intent.call_args.kwargs["mood_text"], "想找二次元周边")

    def test_recommend_routes_endpoint_uses_structured_intent_for_description_alias(self):
        import app as app_module

        intent = {
            "normalized_intent": "想一个人安静待一下午",
            "summary": "想一个人安静待一下午",
            "inferred_tags": ["想一个人静静"],
            "inferred_experience_tags": ["想一个人静静"],
            "inferred_mindset_tags": ["独处"],
            "preferred_scene_types": ["书店", "图书馆", "安静空间"],
            "avoid_scene_types": ["人多"],
            "must_have": ["安静"],
            "soft_preferences": ["低噪音"],
            "route_keywords": ["书店", "安静", "独处"],
            "mood_tone": "想独处",
            "budget_preference": "unknown",
            "crowd_preference": "quiet",
            "time_preference": "day",
            "confidence": 0.92,
            "source": "qwen",
        }
        with (
            patch.object(app_module.qwen_service, "api_key", "test-key"),
            patch.object(app_module.qwen_service, "parse_user_intent_with_llm", return_value=intent) as parse_intent,
        ):
            client = app_module.app.test_client()
            response = client.post(
                "/api/recommend-routes",
                json={
                    "selected_tags": [],
                    "description": "我想一个人安静待一下午",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["needs_input"])
        self.assertEqual(data["intent"], intent)
        self.assertGreater(len(data["routes"]), 0)
        parse_intent.assert_called_once()
        self.assertEqual(parse_intent.call_args.kwargs["mood_text"], "我想一个人安静待一下午")

    def test_recommend_routes_endpoint_returns_multiple_routes(self):
        import app as app_module

        with patch.object(app_module.qwen_service, "api_key", ""):
            client = app_module.app.test_client()
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


def _qwen_scripts_for_routes(routes, user_text, intent, **kwargs):
    scripts = {}
    for route in routes:
        sections = []
        for index, spot in enumerate(route["spots"], start=1):
            spot_name = spot["name"]
            paragraphs = [
                f"{spot_name}让第{index}幕从真实地点展开。",
                f"你可以顺着{spot_name}的节奏慢慢停留。",
            ]
            sections.append(
                {
                    "type": "spot",
                    "spot_id": spot["spot_id"],
                    "spot_name": spot_name,
                    "title": f"第{index}幕｜{spot_name}",
                    "text": "\n\n".join(paragraphs),
                    "paragraphs": paragraphs,
                }
            )
        scripts[route["route_id"]] = {
            "script": f"这是一条由千问生成的真实路线文案，带着情绪经过{'、'.join(spot['name'] for spot in route['spots'])}。",
            "script_title": f"{route['route_name']}的千问剧本",
            "script_sections": sections,
        }
    return scripts


def _first_qwen_script_only(routes, user_text, intent, **kwargs):
    scripts = _qwen_scripts_for_routes(routes, user_text, intent)
    if not routes:
        return {}
    first_route_id = routes[0]["route_id"]
    return {first_route_id: scripts[first_route_id]}


def _first_call_first_route_then_all_remaining():
    calls = []

    def generate(routes, user_text, intent, **kwargs):
        calls.append([route["route_id"] for route in routes])
        if len(calls) == 1:
            return _first_qwen_script_only(routes, user_text, intent, **kwargs)
        return _qwen_scripts_for_routes(routes, user_text, intent, **kwargs)

    return generate


def _first_call_first_route_then_empty_retry():
    calls = []

    def generate(routes, user_text, intent, **kwargs):
        calls.append([route["route_id"] for route in routes])
        if len(calls) == 1:
            return _first_qwen_script_only(routes, user_text, intent, **kwargs)
        return {}

    return generate


if __name__ == "__main__":
    unittest.main()
