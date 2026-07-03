import json
import unittest
from types import SimpleNamespace

from services.qwen_service import QwenService


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=response),
                )
            ]
        )


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class QwenServiceTest(unittest.TestCase):
    def test_parse_user_intent_filters_unknown_tags_and_keeps_structured_preferences(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "normalized_intent": "想在夜晚找一个安静的二次元空间",
                        "inferred_tags": ["想夜晚继续玩", "不存在的标签"],
                        "preferred_scene_types": ["二次元", "安静空间"],
                        "avoid_scene_types": ["人太多"],
                        "must_have": ["周边"],
                        "soft_preferences": ["低预算"],
                        "route_keywords": ["二次元", "IP周边"],
                        "mood_tone": "想探索",
                        "budget_preference": "low",
                        "crowd_preference": "quiet",
                        "time_preference": "night",
                        "confidence": 0.88,
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        intent = service.parse_user_intent_with_llm(
            selected_tags=["想夜晚继续玩"],
            mood_text="想安静一点，也想找二次元周边",
            available_tags=["想夜晚继续玩", "想进入童话/动漫世界"],
            route_summaries=[
                {
                    "route_id": "R30",
                    "route_name": "南京东路二次元补给线",
                    "route_tags": ["想进入童话/动漫世界"],
                    "description": "二次元、IP周边和城市夜游",
                    "scene_tags": ["二次元", "周边"],
                }
            ],
        )

        self.assertEqual(intent["normalized_intent"], "想在夜晚找一个安静的二次元空间")
        self.assertEqual(intent["inferred_tags"], ["想夜晚继续玩"])
        self.assertEqual(intent["preferred_scene_types"], ["二次元", "安静空间"])
        self.assertEqual(intent["avoid_scene_types"], ["人太多"])
        self.assertEqual(intent["budget_preference"], "low")
        self.assertEqual(intent["crowd_preference"], "quiet")
        self.assertEqual(intent["time_preference"], "night")
        self.assertEqual(intent["source"], "qwen")
        self.assertEqual(intent["summary"], intent["normalized_intent"])

        request = client.completions.requests[0]
        prompt = request["messages"][1]["content"]
        self.assertIn("available_tags", prompt)
        self.assertIn("selected_tags", prompt)
        self.assertIn("mood_text", prompt)
        self.assertIn("route_summaries", prompt)
        self.assertIn("南京东路二次元补给线", prompt)

    def test_parse_user_intent_falls_back_on_invalid_json_or_timeout(self):
        for response in ["not-json", TimeoutError("timed out")]:
            with self.subTest(response=response):
                service = QwenService(api_key="test-key", client=FakeClient([response]))

                intent = service.parse_user_intent_with_llm(
                    selected_tags=["想夜晚继续玩"],
                    mood_text="想安静一点",
                    available_tags=["想夜晚继续玩"],
                    route_summaries=[],
                )

                self.assertEqual(intent["normalized_intent"], "想安静一点")
                self.assertEqual(intent["inferred_tags"], ["想夜晚继续玩"])
                self.assertEqual(intent["source"], "fallback")
                self.assertEqual(intent["confidence"], 0)

    def test_analyze_intent_filters_unknown_tags_and_returns_qwen_source(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "summary": "想安静地慢慢走",
                        "experience_tags": ["想一个人静静", "不存在的标签"],
                        "mindset_tags": ["疗愈", "未知心境"],
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        intent = service.analyze_intent(
            "今天有点累，想一个人慢慢走",
            allowed_experience_tags=["想一个人静静", "想慢慢走不赶路"],
            allowed_mindset_tags=["独处", "疗愈"],
        )

        self.assertEqual(intent["summary"], "想安静地慢慢走")
        self.assertEqual(intent["inferred_experience_tags"], ["想一个人静静"])
        self.assertEqual(intent["inferred_mindset_tags"], ["疗愈"])
        self.assertEqual(intent["source"], "qwen")

    def test_analyze_intent_falls_back_on_invalid_json_or_timeout(self):
        for response in ["not-json", TimeoutError("timed out")]:
            with self.subTest(response=response):
                service = QwenService(
                    api_key="test-key",
                    client=FakeClient([response]),
                )

                intent = service.analyze_intent(
                    "想看夜景",
                    allowed_experience_tags=["想被夜景治愈"],
                    allowed_mindset_tags=["浪漫"],
                )

                self.assertEqual(intent["summary"], "想看夜景")
                self.assertEqual(intent["inferred_experience_tags"], [])
                self.assertEqual(intent["inferred_mindset_tags"], [])
                self.assertEqual(intent["source"], "fallback")

    def test_disabled_service_returns_fallback_without_calling_api(self):
        service = QwenService(api_key="", client=FakeClient([]))

        intent = service.analyze_intent(
            "想看展",
            allowed_experience_tags=["想看展充电"],
            allowed_mindset_tags=["灵感"],
        )
        scripts = service.generate_route_scripts(
            routes=[_route("R01", "测试路线")],
            user_text="想看展",
            intent=intent,
        )

        self.assertEqual(intent["source"], "fallback")
        self.assertEqual(scripts, {})
        self.assertEqual(service.last_script_error, "qwen_not_configured")

    def test_generate_route_scripts_returns_structured_sections_and_filters_invalid_items(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "从第一站开始慢慢走，让城市的声音慢下来。",
                                "script_title": "把自己还给自己的半日",
                                "script_sections": [
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜树影先替你慢下来。",
                                        "paragraphs": [
                                            "先把脚步放慢，留意街角的安静。",
                                            "如果不赶时间，可以观察周围的细节。",
                                            "你会发现注意力正在从紧绷切换到可停留。",
                                        ],
                                        "text": "先把脚步放慢，留意街角的安静。\n\n如果不赶时间，可以观察周围的细节。\n\n你会发现注意力正在从紧绷切换到可停留。",
                                    },
                                    {
                                        "type": "spot",
                                        "spot_id": "S02",
                                        "spot_name": "第二站",
                                        "title": "第二幕｜继续往安静里走。",
                                        "paragraphs": [
                                            "再把散步交给下一处可以停留的地方。",
                                            "按原路线走到第二站，把节奏留给自己。",
                                        ],
                                        "text": "再把散步交给下一处可以停留的地方。\n\n按原路线走到第二站，把节奏留给自己。",
                                    },
                                ],
                            },
                            {
                                "route_id": "R02",
                                "script": "这条路线没有合法分幕。",
                                "script_sections": [],
                            },
                            {
                                "route_id": "R99",
                                "script": "这条路线并不存在。",
                                "script_sections": [
                                    {"type": "opening", "title": "开场", "text": "不存在。"}
                                ],
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)
        routes = [_route("R01", "路线一"), _route("R02", "路线二")]
        original_routes = json.loads(json.dumps(routes, ensure_ascii=False))

        scripts = service.generate_route_scripts(
            routes=routes,
            user_text="想安静散步",
            intent={
                "summary": "安静散步",
                "inferred_experience_tags": ["想慢慢走不赶路"],
                "inferred_mindset_tags": ["疗愈"],
                "source": "qwen",
            },
        )

        self.assertEqual(set(scripts), {"R01"})
        script = scripts["R01"]
        self.assertEqual(script["script"], "从第一站开始慢慢走，让城市的声音慢下来。")
        self.assertEqual(script["script_title"], "把自己还给自己的半日")
        self.assertNotIn("script_opening", script)
        self.assertNotIn("script_role", script)
        self.assertNotIn("script_sensory", script)
        self.assertNotIn("script_closing", script)
        self.assertEqual(len(script["script_sections"]), 2)
        self.assertTrue(all(section["type"] == "spot" for section in script["script_sections"]))
        self.assertEqual(script["script_sections"][0]["spot_name"], "第一站")
        self.assertEqual(script["script_sections"][0]["paragraphs"][0], "先把脚步放慢，留意街角的安静。")
        self.assertEqual(service.last_script_error, "qwen_incomplete_response")
        self.assertEqual(routes, original_routes)

    def test_generate_route_scripts_prompt_includes_immersive_route_context(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "从第一站开始慢慢走，让城市的声音慢下来。",
                                "script_title": "把自己还给自己的半日",
                                "script_sections": [
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜树影先替你慢下来。",
                                        "text": "第一幕。",
                                        "paragraphs": ["第一幕。"],
                                    },
                                    {
                                        "type": "spot",
                                        "spot_id": "S02",
                                        "spot_name": "第二站",
                                        "title": "第二幕｜继续往安静里走。",
                                        "text": "第二幕。",
                                        "paragraphs": ["第二幕。"],
                                    },
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        service.generate_route_scripts(
            routes=[_route("R01", "测试路线")],
            user_text="想安静散步",
            intent={
                "summary": "安静散步",
                "normalized_intent": "安静散步",
                "inferred_experience_tags": ["想慢慢走不赶路"],
                "inferred_mindset_tags": ["疗愈"],
                "route_keywords": ["安静"],
                "source": "qwen",
            },
            selected_tags=["想一个人静静"],
            mood_text="想安静散步",
        )

        request = client.completions.requests[0]
        user_prompt = request["messages"][1]["content"]
        self.assertIn("用户心境为主线", user_prompt)
        self.assertIn("不要生成普通旅游攻略", user_prompt)
        self.assertIn("按点位分幕", user_prompt)
        self.assertIn("剧本标题", user_prompt)
        self.assertNotIn("开场白", user_prompt)
        self.assertNotIn("角色设定", user_prompt)
        self.assertNotIn("感官描写", user_prompt)
        self.assertNotIn("结尾收束", user_prompt)
        self.assertIn("上海独处路线推荐", user_prompt)
        self.assertIn("paragraphs", user_prompt)
        self.assertIn("ai_script_angle", user_prompt)
        self.assertIn("suitable_mood", user_prompt)
        self.assertIn("feedback_keywords", user_prompt)
        self.assertIn("coverage_policy", user_prompt)
        self.assertIn("required_route_ids", user_prompt)
        self.assertIn("selected_tags", user_prompt)
        self.assertIn("mood_text", user_prompt)
        self.assertIn("intent_json", user_prompt)
        self.assertIn("candidate_routes", user_prompt)
        self.assertIn("candidate_spots", user_prompt)
        self.assertIn('"R01"', user_prompt)

    def test_generate_route_scripts_uses_longer_timeout_for_script_generation(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "从第一站开始慢慢走，让城市的声音慢下来。",
                                "script_title": "把自己还给自己的半日",
                                "script_sections": [
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜树影先替你慢下来。",
                                        "text": "第一幕。",
                                        "paragraphs": ["第一幕。"],
                                    },
                                    {
                                        "type": "spot",
                                        "spot_id": "S02",
                                        "spot_name": "第二站",
                                        "title": "第二幕｜继续往安静里走。",
                                        "text": "第二幕。",
                                        "paragraphs": ["第二幕。"],
                                    },
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", timeout_seconds=20, client=client)

        service.generate_route_scripts(
            routes=[_route("R01", "测试路线")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        request = client.completions.requests[0]
        self.assertGreaterEqual(request["timeout"], 45)

    def test_generate_route_scripts_ignores_invalid_structured_response(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "这条路线缺少合法分幕。",
                                "script_sections": "not-a-list",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        scripts = service.generate_route_scripts(
            routes=[_route("R01", "路线一")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        self.assertEqual(scripts, {})
        self.assertEqual(service.last_script_error, "qwen_incomplete_response")

    def test_generate_route_scripts_records_request_failure(self):
        service = QwenService(api_key="test-key", client=FakeClient([TimeoutError("timed out")]))

        scripts = service.generate_route_scripts(
            routes=[_route("R01", "路线一")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        self.assertEqual(scripts, {})
        self.assertEqual(service.last_script_error, "qwen_request_failed")

    def test_generate_route_scripts_records_invalid_json_as_invalid_response(self):
        service = QwenService(api_key="test-key", client=FakeClient(["not-json"]))

        scripts = service.generate_route_scripts(
            routes=[_route("R01", "路线一")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        self.assertEqual(scripts, {})
        self.assertEqual(service.last_script_error, "qwen_invalid_response")

    def test_generate_route_scripts_allows_partial_spot_sections_in_route_order(self):
        client = FakeClient(
            [
                json.dumps(
                    {
                        "scripts": [
                            {
                                "route_id": "R01",
                                "script": "这条路线先从第一站慢慢展开。",
                                "script_title": "把第一束安静留给自己",
                                "script_sections": [
                                    {
                                        "type": "spot",
                                        "spot_id": "S01",
                                        "spot_name": "第一站",
                                        "title": "第一幕｜第一站",
                                        "text": "第一幕。",
                                        "paragraphs": ["第一幕。"],
                                    }
                                ],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        service = QwenService(api_key="test-key", client=client)

        scripts = service.generate_route_scripts(
            routes=[_route("R01", "路线一")],
            user_text="想安静散步",
            intent={"summary": "安静散步", "source": "qwen"},
        )

        self.assertEqual(set(scripts), {"R01"})
        self.assertEqual(len(scripts["R01"]["script_sections"]), 1)
        self.assertEqual(scripts["R01"]["script_sections"][0]["spot_id"], "S01")
        self.assertEqual(service.last_script_error, "")

    def test_generate_route_scripts_rejects_story_sections_and_out_of_order_spots(self):
        invalid_responses = [
            {
                "scripts": [
                    {
                        "route_id": "R01",
                        "script": "这条路线混入了开场和收束。",
                        "script_title": "混入无效段落的剧本",
                        "script_sections": [
                            {"type": "opening", "title": "开场", "text": "开场。"},
                            {
                                "type": "spot",
                                "spot_id": "S01",
                                "spot_name": "第一站",
                                "title": "第一幕｜第一站",
                                "text": "第一幕。",
                                "paragraphs": ["第一幕。"],
                            },
                            {"type": "closing", "title": "收束", "text": "收束。"},
                        ],
                    }
                ]
            },
            {
                "scripts": [
                    {
                        "route_id": "R01",
                        "script": "这条路线把第二站写到了第一站前面。",
                        "script_title": "顺序错乱的剧本",
                        "script_sections": [
                            {
                                "type": "spot",
                                "spot_id": "S02",
                                "spot_name": "第二站",
                                "title": "第一幕｜第二站",
                                "text": "第二站。",
                                "paragraphs": ["第二站。"],
                            },
                            {
                                "type": "spot",
                                "spot_id": "S01",
                                "spot_name": "第一站",
                                "title": "第二幕｜第一站",
                                "text": "第一站。",
                                "paragraphs": ["第一站。"],
                            },
                        ],
                    }
                ]
            },
        ]

        for response in invalid_responses:
            with self.subTest(response=response["scripts"][0]["script_title"]):
                client = FakeClient([json.dumps(response, ensure_ascii=False)])
                service = QwenService(api_key="test-key", client=client)

                scripts = service.generate_route_scripts(
                    routes=[_route("R01", "路线一")],
                    user_text="想安静散步",
                    intent={"summary": "安静散步", "source": "qwen"},
                )

                self.assertEqual(scripts, {})
                self.assertEqual(service.last_script_error, "qwen_incomplete_response")

def _route(route_id, name):
    return {
        "route_id": route_id,
        "route_name": name,
        "route_intro_user_facing": "适合慢慢预览的一条路线。",
        "suitable_mood": "想独处、想散心",
        "ai_script_angle": "一个人的城市信件",
        "matched_tags": ["想一个人静静"],
        "matched_mindsets": ["疗愈"],
        "match_reason": "符合此刻的心情",
        "spots": [
            {
                "spot_id": "S01",
                "name": "第一站",
                "description": "安静的街角",
                "open_time": "全天",
                "ticket_reservation": "免费",
                "feedback_keywords": ["安静", "慢走"],
            },
            {
                "spot_id": "S02",
                "name": "第二站",
                "description": "适合散步",
                "open_time": "全天",
                "ticket_reservation": "免费",
                "feedback_keywords": ["停留", "放松"],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
