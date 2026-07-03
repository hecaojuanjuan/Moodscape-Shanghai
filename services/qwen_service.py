import json
import os
import sys
import traceback


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.5-plus"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_SCRIPT_TIMEOUT_SECONDS = 45.0


class QwenInvalidResponseError(ValueError):
    pass


class QwenService:
    def __init__(
        self,
        api_key=None,
        base_url=None,
        model=None,
        timeout_seconds=None,
        client=None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("QWEN_API_KEY", "")
        self.base_url = base_url or os.getenv("QWEN_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.getenv("QWEN_MODEL", DEFAULT_MODEL)
        self.timeout_seconds = _positive_float(
            timeout_seconds if timeout_seconds is not None else os.getenv("LLM_TIMEOUT_SECONDS"),
            DEFAULT_TIMEOUT_SECONDS,
        )
        self._provided_client = client
        self._client_instance = None
        self.last_script_error = ""

    @property
    def enabled(self):
        return bool(self.api_key.strip())

    def log_exception(self, exc):
        self._log_request_failure(exc)

    def analyze_intent(self, user_text, allowed_experience_tags, allowed_mindset_tags):
        fallback = _fallback_intent(user_text)
        if not self.enabled:
            self._log_request_skipped("Qwen API key is empty.")
            return fallback
        if not str(user_text or "").strip():
            return fallback

        prompt = {
            "task": "分析用户在上海旅行时此刻的体验需求，只能从给定标签中选择。",
            "user_text": str(user_text).strip(),
            "allowed_experience_tags": list(allowed_experience_tags or []),
            "allowed_mindset_tags": list(allowed_mindset_tags or []),
            "output_schema": {
                "summary": "不超过40字的中文摘要",
                "experience_tags": ["零个或多个允许的体验标签"],
                "mindset_tags": ["零个或多个允许的心境标签"],
            },
        }

        try:
            result = self._request_json(
                system_prompt=(
                    "你是旅行意图解析器。必须返回 JSON 对象，不得输出 Markdown；"
                    "不得创造输入列表之外的标签。"
                ),
                user_prompt=json.dumps(prompt, ensure_ascii=False),
                max_tokens=500,
            )
        except Exception as exc:
            self._log_request_failure(exc)
            return fallback

        experience_tags = _filter_allowed(
            result.get("experience_tags"),
            allowed_experience_tags,
        )
        mindset_tags = _filter_allowed(
            result.get("mindset_tags"),
            allowed_mindset_tags,
        )
        summary = _clean_text(result.get("summary")) or fallback["summary"]
        return {
            "summary": summary[:80],
            "inferred_experience_tags": experience_tags,
            "inferred_mindset_tags": mindset_tags,
            "source": "qwen",
        }

    def generate_route_scripts(self, routes, user_text, intent):
        self.last_script_error = ""
        if not self.enabled:
            self.last_script_error = "qwen_not_configured"
            self._log_request_skipped("Qwen API key is empty.")
            return {}
        if not routes:
            return {}

        route_payloads = [_route_prompt_payload(route) for route in routes]
        required_route_ids = [
            payload["route_id"]
            for payload in route_payloads
            if payload.get("route_id")
        ]
        request_payload = {
            "task": "为候选上海路线分别生成按点位分幕的沉浸旅行剧本：以用户心境为主线、以真实城市点位为场景、以情绪变化为结构。不要生成普通旅游攻略。",
            "user_text": str(user_text or "").strip(),
            "intent": intent or {},
            "routes": route_payloads,
            "coverage_policy": {
                "required_route_ids": required_route_ids,
                "required_scripts_count": len(required_route_ids),
                "rule": "Return exactly one complete script object for every required_route_id. Do not stop after the first or best route.",
            },
            "rules": [
                "scripts must include every route_id listed in coverage_policy.required_route_ids exactly once.",
                "每个 route_id 最多返回一组剧本。",
                "只能使用输入中提供的路线和点位。",
                "不得新增景点、改变点位顺序或虚构开放时间、票务信息、历史事件。",
                "不要生成普通旅游攻略、景点百科、交通清单、营销广告或泛泛的打卡建议。",
                "每条路线只输出剧本标题和按真实点位排列的分幕正文。",
                "禁止输出开场、人物身份、单独感官清单或路线收尾；不要把这些内容放进 script_sections。",
                "script_title 必须有情绪和画面感，禁止只用地点名、路线名、上海独处路线推荐或任何包含“路线推荐”的标题。",
                "整体使用第二人称，像城市剧本编辑在帮用户预演一段心境变化，不写现场导航命令。",
                "script 是兼容旧展示的一段沉浸式路线摘要，约120至200字，必须写出真实点位名和情绪变化。",
                "script_sections 只能包含 type 为 spot 的分幕。优先覆盖输入 spots 中前 4 个点位；如果点位很多，不必覆盖所有点位，但必须保持输入顺序。",
                "每一幕标题要短而有情绪，可写成“第一幕｜宇宙仍在头顶。”这样的形式。",
                "每一幕必须包含 title、text、paragraphs、spot_id、spot_name；paragraphs 为 2 至 3 段中文短段落。",
                "每一幕只引用对应点位事实，可写感官与心境，但不能添加未提供事实。",
                "每段不超过 90 个中文字符，保持慢节奏、有画面感，不写成攻略说明。",
            ],
            "output_schema": {
                "scripts": [
                    {
                        "route_id": "输入中的 route_id",
                        "script": "兼容旧展示的一段沉浸式路线摘要",
                        "script_title": "有情绪的剧本标题，如《把自己还给自己的半日》",
                        "script_sections": [
                            {
                                "type": "spot",
                                "spot_id": "输入中的 spot_id",
                                "spot_name": "输入中的 spot_name",
                                "title": "第一幕｜宇宙仍在头顶。",
                                "paragraphs": [
                                    "从这里开始，城市熟悉的节奏被轻轻放远。",
                                    "如果不赶时间，可以挑一个最想看的角落慢慢停留。",
                                    "也许你会发现，今天放松下来的不是身体，而是一直紧绷的注意力。"
                                ],
                                "text": "把 paragraphs 用两个空行连接后的完整正文",
                            },
                        ],
                    }
                ]
            },
        }

        try:
            result = self._request_json(
                system_prompt=(
                    "你是上海城市旅行剧本编辑。必须严格依据输入事实并返回 JSON 对象，"
                    "不得输出 Markdown，不得把路线写成营销广告、景点百科或普通旅游攻略。"
                ),
                user_prompt=json.dumps(request_payload, ensure_ascii=False),
                max_tokens=6000,
                temperature=0.45,
                timeout_seconds=max(self.timeout_seconds, DEFAULT_SCRIPT_TIMEOUT_SECONDS),
            )
        except QwenInvalidResponseError as exc:
            self._log_request_failure(exc)
            self.last_script_error = "qwen_invalid_response"
            return {}
        except Exception as exc:
            self._log_request_failure(exc)
            self.last_script_error = "qwen_request_failed"
            return {}

        allowed_routes = {
            route.get("route_id"): route
            for route in routes
            if isinstance(route, dict) and route.get("route_id")
        }
        scripts = {}
        raw_scripts = result.get("scripts")
        if not isinstance(raw_scripts, list):
            self.last_script_error = "qwen_invalid_response"
            return scripts

        for item in raw_scripts:
            if not isinstance(item, dict):
                continue
            route_id = _clean_text(item.get("route_id"))
            if route_id not in allowed_routes or route_id in scripts:
                continue
            script_payload = _clean_script_payload(item, allowed_routes[route_id])
            if script_payload:
                scripts[route_id] = script_payload
        if len(scripts) < len(allowed_routes):
            self.last_script_error = "qwen_incomplete_response"
        return scripts

    def _request_json(
        self,
        system_prompt,
        user_prompt,
        max_tokens,
        temperature=0.2,
        timeout_seconds=None,
    ):
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout_seconds or self.timeout_seconds,
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise QwenInvalidResponseError("Qwen response did not include message content.") from exc
        try:
            parsed = json.loads(_strip_code_fence(content))
        except json.JSONDecodeError as exc:
            raise QwenInvalidResponseError("Qwen response content was not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise QwenInvalidResponseError("Qwen response must be a JSON object.")
        return parsed

    def _get_client(self):
        if self._provided_client is not None:
            return self._provided_client
        if self._client_instance is None:
            from openai import OpenAI

            self._client_instance = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        return self._client_instance

    def _log_request_failure(self, exc):
        _log_qwen_exception(
            exc=exc,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_seconds=self.timeout_seconds,
        )

    def _log_request_skipped(self, reason):
        print("======== Qwen Request Skipped ========", file=sys.stderr)
        print("Reason:", file=sys.stderr)
        print(reason, file=sys.stderr)
        print("Model:", file=sys.stderr)
        print(self.model, file=sys.stderr)
        print("Base URL:", file=sys.stderr)
        print(self.base_url, file=sys.stderr)
        print("API Key Exists:", file=sys.stderr)
        print(bool(str(self.api_key or "").strip()), file=sys.stderr)
        print("Timeout Seconds:", file=sys.stderr)
        print(self.timeout_seconds, file=sys.stderr)
        print("====================================", file=sys.stderr)


def _fallback_intent(user_text):
    return {
        "summary": _clean_text(user_text)[:80],
        "inferred_experience_tags": [],
        "inferred_mindset_tags": [],
        "source": "fallback",
    }


def _filter_allowed(values, allowed_values):
    if not isinstance(values, list):
        return []
    allowed = set(allowed_values or [])
    filtered = []
    for value in values:
        clean_value = _clean_text(value)
        if clean_value in allowed and clean_value not in filtered:
            filtered.append(clean_value)
    return filtered


def _route_prompt_payload(route):
    return {
        "route_id": route.get("route_id", ""),
        "route_name": route.get("route_name", ""),
        "route_intro_user_facing": route.get("route_intro_user_facing", ""),
        "suitable_mood": route.get("suitable_mood", ""),
        "estimated_time": route.get("estimated_time", ""),
        "budget_level": route.get("budget_level", ""),
        "route_spots": route.get("route_spots", ""),
        "ai_script_angle": route.get("ai_script_angle", ""),
        "match_reason": route.get("match_reason", ""),
        "matched_tags": route.get("matched_tags", []),
        "matched_mindsets": route.get("matched_mindsets", []),
        "dominant_mindsets": route.get("dominant_mindsets", []),
        "spots": [
            {
                "spot_id": spot.get("spot_id", ""),
                "spot_order": spot.get("spot_order", ""),
                "name": spot.get("name", ""),
                "description": spot.get("description", ""),
                "district": spot.get("district", ""),
                "open_time": spot.get("open_time", ""),
                "ticket_reservation": spot.get("ticket_reservation", ""),
                "feedback_keywords": spot.get("feedback_keywords", []),
                "address": spot.get("address", ""),
            }
            for spot in route.get("spots", [])
        ],
    }


def _clean_script_payload(item, route):
    script = _clean_text(item.get("script"))
    script_title = _clean_text(item.get("script_title"))
    sections = _clean_script_sections(item.get("script_sections"), route)
    if (
        not script
        or _is_weak_script_title(script_title, route)
        or not sections
    ):
        return None
    return {
        "script": script,
        "script_title": script_title,
        "script_sections": sections,
    }


def _is_weak_script_title(title, route):
    if not title:
        return True
    route_name = _clean_text(route.get("route_name"))
    return title == route_name or "路线推荐" in title


def _clean_script_sections(raw_sections, route):
    if not isinstance(raw_sections, list):
        return []

    allowed_spots = route.get("spots", [])
    spots_by_id = {
        _clean_text(spot.get("spot_id")): spot
        for spot in allowed_spots
        if _clean_text(spot.get("spot_id"))
    }
    spots_by_name = {
        _clean_text(spot.get("name")): spot
        for spot in allowed_spots
        if _clean_text(spot.get("name"))
    }
    expected_spot_keys = [
        _route_spot_key(spot)
        for spot in allowed_spots
        if _route_spot_key(spot)
    ]

    sections = []
    section_spot_keys = []
    has_spot = False
    has_non_spot_story_section = False
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        section_type = _clean_text(section.get("type"))
        if section_type in {"opening", "closing"}:
            has_non_spot_story_section = True
            continue
        if section_type != "spot":
            continue

        title = _clean_text(section.get("title"))
        text = _clean_text(section.get("text"))
        paragraphs = _clean_script_paragraphs(section.get("paragraphs"), text)
        if not title or not text or not paragraphs:
            continue

        spot_id = _clean_text(section.get("spot_id"))
        spot_name = _clean_text(section.get("spot_name"))
        matched_spot = None
        if spot_id:
            matched_spot = spots_by_id.get(spot_id)
        if not matched_spot and spot_name:
            matched_spot = spots_by_name.get(spot_name)
        if not matched_spot:
            continue
        clean_section = {
            "type": "spot",
            "spot_id": _clean_text(matched_spot.get("spot_id")),
            "spot_name": _clean_text(matched_spot.get("name")),
            "title": title,
            "text": text,
            "paragraphs": paragraphs,
        }
        section_spot_keys.append(_route_spot_key(matched_spot))
        has_spot = True
        sections.append(clean_section)

    if has_non_spot_story_section or not has_spot:
        return []
    # 放宽校验：千问只要返回了有效 spot 分幕，就不要因为没有覆盖全部点位而回退到本地模板。
    # 原逻辑要求 section_spot_keys 必须与 expected_spot_keys 完全一致，路线点位较多时很容易触发 qwen_incomplete_response。
    if expected_spot_keys and not section_spot_keys:
        return []
    return sections


def _clean_script_paragraphs(raw_paragraphs, fallback_text):
    if isinstance(raw_paragraphs, list):
        paragraphs = [
            _clean_text(paragraph)
            for paragraph in raw_paragraphs
            if _clean_text(paragraph)
        ]
        if paragraphs:
            return paragraphs
    text = _clean_text(fallback_text)
    if not text:
        return []
    paragraphs = [
        paragraph.strip()
        for paragraph in text.replace("\r\n", "\n").split("\n\n")
        if paragraph.strip()
    ]
    return paragraphs or [text]


def _route_spot_key(spot):
    spot_id = _clean_text(spot.get("spot_id"))
    if spot_id:
        return f"id:{spot_id}"
    spot_name = _clean_text(spot.get("name"))
    if spot_name:
        return f"name:{spot_name}"
    return ""


def _strip_code_fence(value):
    text = str(value or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def _clean_text(value):
    return str(value or "").strip()


def _log_qwen_exception(exc, model, base_url, api_key, timeout_seconds=None):
    print("======== Qwen Request Failed ========", file=sys.stderr)
    print("Exception Type:", file=sys.stderr)
    print(type(exc).__name__, file=sys.stderr)
    print("Exception Message:", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    print("Traceback:", file=sys.stderr)
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    print("Model:", file=sys.stderr)
    print(model, file=sys.stderr)
    print("Base URL:", file=sys.stderr)
    print(base_url, file=sys.stderr)
    print("API Key Exists:", file=sys.stderr)
    print(bool(str(api_key or "").strip()), file=sys.stderr)
    if timeout_seconds is not None:
        print("Timeout Seconds:", file=sys.stderr)
        print(timeout_seconds, file=sys.stderr)
    print("====================================", file=sys.stderr)


def _positive_float(value, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback
