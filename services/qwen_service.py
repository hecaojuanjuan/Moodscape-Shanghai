import json
import os


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.5-plus"
DEFAULT_TIMEOUT_SECONDS = 20.0


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

    @property
    def enabled(self):
        return bool(self.api_key.strip())

    def analyze_intent(self, user_text, allowed_experience_tags, allowed_mindset_tags):
        fallback = _fallback_intent(user_text)
        if not self.enabled or not str(user_text or "").strip():
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
        except Exception:
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
        if not self.enabled or not routes:
            return {}

        route_payloads = [_route_prompt_payload(route) for route in routes]
        request_payload = {
            "task": "为候选上海路线分别生成六段式沉浸旅行剧本：以用户心境为主线、以真实城市点位为场景、以情绪变化为结构。不要生成普通旅游攻略。",
            "user_text": str(user_text or "").strip(),
            "intent": intent or {},
            "routes": route_payloads,
            "rules": [
                "每个 route_id 最多返回一组剧本。",
                "只能使用输入中提供的路线和点位。",
                "不得新增景点、改变点位顺序或虚构开放时间、票务信息、历史事件。",
                "不要生成普通旅游攻略、景点百科、交通清单、营销广告或泛泛的打卡建议。",
                "每条路线必须输出 6 个固定部分：剧本标题、开场白、角色设定、分幕路线、感官描写、结尾收束。",
                "script_title 必须有情绪和画面感，禁止只用地点名、路线名、上海独处路线推荐或任何包含“路线推荐”的标题。",
                "script_opening 是开场白，要像把用户拉进故事里，回答“为什么适合此刻的你”。",
                "script_role 是角色设定，默认用户是“今天的主角”，强调不需要完成任务，只需要跟着城市节奏慢下来。",
                "script_sensory 是感官描写，必须包含 see、hear、smell、do，分别写看到什么、听到什么、闻到什么、做什么。",
                "script_closing 是结尾收束，必须写情绪落点，不写成攻略总结。",
                "整体使用第二人称，像城市剧本编辑在帮用户预演一段心境变化，不写现场导航命令。",
                "script 是兼容旧展示的一段沉浸式路线摘要，约180至260字，必须写出真实点位名和情绪变化。",
                "script_sections 必须包含 opening、按输入点位顺序排列的 spot 分幕、closing。",
                "每一幕必须包含 text、emotion_experience、action_guide、scene_image 四个中文字段。",
                "emotion_experience 写用户在该幕里的情绪体验和变化；action_guide 写轻量行动引导；scene_image 写可感知的场景画面。",
                "spot 分幕还必须包含 location、experience、emotion_shift；location 必须是对应真实点位名，experience 写慢走、停留、拍照、写字、发呆等行动体验，emotion_shift 写从什么情绪走向什么情绪。",
                "spot 分幕只能引用对应点位事实，可写感官与心境，但不能添加未提供事实。",
            ],
            "output_schema": {
                "scripts": [
                    {
                        "route_id": "输入中的 route_id",
                        "script": "兼容旧展示的一段沉浸式路线剧本",
                        "script_title": "有情绪的剧本标题，如《把自己还给自己的半日》",
                        "script_opening": "开场白：为什么这条路线适合用户此刻的心情",
                        "script_role": "角色设定：今天的你是今天的主角",
                        "script_sensory": {
                            "see": "看到什么：树影、街灯、建筑、橱窗、河面等来自真实点位的画面",
                            "hear": "听到什么：脚步声、风声、咖啡机声、远处车流等",
                            "smell": "闻到什么：咖啡、雨后路面、植物、老街区等",
                            "do": "做什么：慢走、停留、拍照、写字、听歌、发呆等",
                        },
                        "script_closing": "结尾收束：写情绪落点，不写攻略总结",
                        "script_sections": [
                            {
                                "type": "opening",
                                "title": "开场",
                                "text": "进入路线前的情绪开场",
                                "emotion_experience": "用户此刻心境如何被路线接住",
                                "action_guide": "出发前如何调整节奏",
                                "scene_image": "这条路线即将展开的城市画面",
                            },
                            {
                                "type": "spot",
                                "spot_id": "输入中的 spot_id",
                                "spot_name": "输入中的 spot_name",
                                "title": "第一幕｜点位名",
                                "text": "该点位的预览分幕",
                                "location": "对应真实点位名",
                                "experience": "在该点位可以进行的行动体验",
                                "emotion_shift": "从某种心境转向某种心境",
                                "emotion_experience": "这一站带来的情绪体验和变化",
                                "action_guide": "用户在这一站可以做的轻量行动",
                                "scene_image": "基于该点位事实的场景画面",
                            },
                            {
                                "type": "closing",
                                "title": "收束",
                                "text": "走完路线后的情绪收束",
                                "emotion_experience": "路线结束后的心境变化",
                                "action_guide": "离开前如何把体验带走",
                                "scene_image": "路线回望时留下的城市画面",
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
                max_tokens=3600,
                temperature=0.45,
            )
        except Exception:
            return {}

        allowed_routes = {
            route.get("route_id"): route
            for route in routes
            if isinstance(route, dict) and route.get("route_id")
        }
        scripts = {}
        raw_scripts = result.get("scripts")
        if not isinstance(raw_scripts, list):
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
        return scripts

    def _request_json(self, system_prompt, user_prompt, max_tokens, temperature=0.2):
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout_seconds,
        )
        content = response.choices[0].message.content
        parsed = json.loads(_strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("Qwen response must be a JSON object.")
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
    script_opening = _clean_text(item.get("script_opening"))
    script_role = _clean_text(item.get("script_role"))
    script_sensory = _clean_script_sensory(item.get("script_sensory"))
    script_closing = _clean_text(item.get("script_closing"))
    sections = _clean_script_sections(item.get("script_sections"), route)
    if (
        not script
        or _is_weak_script_title(script_title, route)
        or not script_opening
        or not script_role
        or not script_sensory
        or not script_closing
        or not sections
    ):
        return None
    return {
        "script": script,
        "script_title": script_title,
        "script_opening": script_opening,
        "script_role": script_role,
        "script_sensory": script_sensory,
        "script_closing": script_closing,
        "script_sections": sections,
    }


def _clean_script_sensory(raw_sensory):
    if not isinstance(raw_sensory, dict):
        return {}
    sensory = {}
    for key in ("see", "hear", "smell", "do"):
        value = _clean_text(raw_sensory.get(key))
        if not value:
            return {}
        sensory[key] = value
    return sensory


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
    has_opening = False
    has_spot = False
    has_closing = False
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        section_type = _clean_text(section.get("type"))
        if section_type not in {"opening", "spot", "closing"}:
            continue

        title = _clean_text(section.get("title"))
        text = _clean_text(section.get("text"))
        if not title or not text:
            continue

        clean_section = {
            "type": section_type,
            "title": title,
            "text": text,
        }
        for detail_key in ("emotion_experience", "action_guide", "scene_image"):
            detail_value = _clean_text(section.get(detail_key))
            if detail_value:
                clean_section[detail_key] = detail_value
        if section_type == "spot":
            spot_id = _clean_text(section.get("spot_id"))
            spot_name = _clean_text(section.get("spot_name"))
            matched_spot = None
            if spot_id:
                matched_spot = spots_by_id.get(spot_id)
            if not matched_spot and spot_name:
                matched_spot = spots_by_name.get(spot_name)
            if not matched_spot:
                continue
            clean_section["spot_id"] = _clean_text(matched_spot.get("spot_id"))
            clean_section["spot_name"] = _clean_text(matched_spot.get("name"))
            clean_section["location"] = _clean_text(section.get("location")) or clean_section["spot_name"]
            clean_section["experience"] = (
                _clean_text(section.get("experience"))
                or clean_section.get("action_guide", "")
            )
            clean_section["emotion_shift"] = (
                _clean_text(section.get("emotion_shift"))
                or clean_section.get("emotion_experience", "")
            )
            section_spot_keys.append(_route_spot_key(matched_spot))
            has_spot = True
        elif section_type == "opening":
            has_opening = True
        elif section_type == "closing":
            has_closing = True
        sections.append(clean_section)

    if not (has_opening and has_spot and has_closing):
        return []
    if expected_spot_keys and section_spot_keys != expected_spot_keys:
        return []
    return sections


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


def _positive_float(value, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback
