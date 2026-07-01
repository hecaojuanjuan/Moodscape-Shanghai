import os

from flask import Flask, jsonify, render_template, request

from services.recommender import load_mindset_tags, load_tags, recommend_route, recommend_routes
from services.qwen_service import QwenService


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


NEEDS_INPUT_MESSAGE = "请在左侧选择标签，或者写入你的心情状态。"


app = Flask(__name__)
qwen_service = QwenService()


@app.get("/")
def index():
    return render_template(
        "index.html",
        frontend_config={
            "amapJsKey": os.getenv("AMAP_JS_KEY", ""),
            "amapSecurityJsCode": os.getenv("AMAP_SECURITY_JS_CODE", ""),
        },
    )


@app.get("/api/tags")
def tags_api():
    return jsonify(
        {
            "experience_tags": load_tags(),
            "mindset_tags": load_mindset_tags(),
        }
    )


@app.post("/api/generate-script")
def generate_script_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, user_text, profile_answers = _read_recommendation_payload(payload)
    if _needs_current_input(selected_tags, user_text):
        return jsonify(_needs_input_response(include_script=True))

    intent = _analyze_intent(user_text)
    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=user_text,
        profile_answers=profile_answers,
        inferred_experience_tags=intent["inferred_experience_tags"],
        inferred_mindset_tags=intent["inferred_mindset_tags"],
        limit=3,
    )
    generated_scripts = _generate_route_scripts(routes, user_text, intent)
    for route in routes:
        generated_script = generated_scripts.get(route.get("route_id"))
        uses_qwen_script = _script_payload_is_complete(generated_script, route)
        script_payload = generated_script if uses_qwen_script else generate_excel_script_payload(route, user_text, intent)
        _apply_script_payload(route, script_payload)
        route["script_source"] = "qwen" if uses_qwen_script else "fallback"

    first_route = routes[0] if routes else {}
    return jsonify(
        {
            "routes": routes,
            "route": first_route,
            "script": first_route.get("script", ""),
            "script_sections": first_route.get("script_sections", []),
            "needs_input": False,
            "message": "",
            "matched_tags": first_route.get("matched_tags", []),
            "matched_mindsets": first_route.get("matched_mindsets", []),
            "recommendation_reason": first_route.get("match_reason", ""),
            "spots": first_route.get("spots", []),
            "intent": intent,
        }
    )


@app.post("/api/recommend-routes")
def recommend_routes_api():
    payload = request.get_json(silent=True) or {}
    selected_tags, user_text, profile_answers = _read_recommendation_payload(payload)
    if _needs_current_input(selected_tags, user_text):
        return jsonify(_needs_input_response())

    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=user_text,
        profile_answers=profile_answers,
        limit=3,
    )
    return jsonify({"routes": routes, "needs_input": False, "message": ""})


def _read_recommendation_payload(payload):
    selected_tags = payload.get("selected_tags", [])
    user_text = payload.get("user_text", "")
    profile_answers = payload.get("profile_answers", {})

    if not isinstance(selected_tags, list):
        selected_tags = []
    if not isinstance(user_text, str):
        user_text = ""
    if not isinstance(profile_answers, dict):
        profile_answers = {}

    selected_tags = [tag.strip() for tag in selected_tags if isinstance(tag, str) and tag.strip()]
    profile_answers = {
        key: value
        for key, value in profile_answers.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    return selected_tags, user_text.strip(), profile_answers


def _needs_current_input(selected_tags, user_text):
    return not selected_tags and not user_text.strip()


def _needs_input_response(include_script=False):
    response = {
        "routes": [],
        "needs_input": True,
        "message": NEEDS_INPUT_MESSAGE,
    }
    if include_script:
        response.update(
            {
                "route": {},
                "script": "",
                "script_sections": [],
                "matched_tags": [],
                "matched_mindsets": [],
                "recommendation_reason": "",
                "spots": [],
                "intent": _fallback_intent(""),
            }
        )
    return response


def _analyze_intent(user_text):
    experience_tags = [
        tag["emotion_tag"]
        for tag in load_tags()
        if tag.get("emotion_tag")
    ]
    mindset_tags = load_mindset_tags()
    try:
        return qwen_service.analyze_intent(
            user_text,
            allowed_experience_tags=experience_tags,
            allowed_mindset_tags=mindset_tags,
        )
    except Exception:
        return _fallback_intent(user_text)


def _generate_route_scripts(routes, user_text, intent):
    try:
        return qwen_service.generate_route_scripts(routes, user_text, intent)
    except Exception:
        return {}


def _fallback_intent(user_text):
    return {
        "summary": str(user_text or "").strip()[:80],
        "inferred_experience_tags": [],
        "inferred_mindset_tags": [],
        "source": "fallback",
    }


SCRIPT_PAYLOAD_KEYS = (
    "script",
    "script_sections",
    "script_title",
)


def _apply_script_payload(route, script_payload):
    for key in SCRIPT_PAYLOAD_KEYS:
        route[key] = script_payload.get(key, [] if key == "script_sections" else "")


def _script_payload_is_complete(script_payload, route=None):
    if not isinstance(script_payload, dict):
        return False
    sections = script_payload.get("script_sections")
    if not all(
        [
            script_payload.get("script"),
            script_payload.get("script_title"),
            isinstance(sections, list),
            sections,
            all(
                isinstance(section, dict)
                and section.get("type") == "spot"
                and section.get("title")
                and section.get("text")
                and section.get("paragraphs")
                for section in sections
            ),
        ]
    ):
        return False

    expected_spot_keys = [_spot_key(spot) for spot in (route or {}).get("spots", []) if _spot_key(spot)]
    section_spot_keys = [_spot_key(section) for section in sections if _spot_key(section)]
    return not expected_spot_keys or section_spot_keys == expected_spot_keys


def generate_excel_script_payload(route, user_text="", intent=None):
    if not route:
        return {
            "script": "",
            "script_sections": [],
            "script_title": "",
        }

    context = _script_context(route, user_text, intent)
    sections = generate_excel_script_sections(route, user_text, intent, context=context)
    script_title = _script_title(route, context)
    script = generate_excel_script(
        route,
        sections,
        script_title=script_title,
    )
    return {
        "script": script,
        "script_sections": sections,
        "script_title": script_title,
    }


def generate_excel_script(
    route,
    script_sections=None,
    script_title="",
):
    if not route:
        return ""

    sections = script_sections or generate_excel_script_sections(route)
    spot_names = [
        section.get("spot_name", "")
        for section in sections
        if section.get("type") == "spot" and section.get("spot_name")
    ]
    scene_lines = [
        _first_paragraph(section)
        for section in sections
        if section.get("type") == "spot"
    ][:3]

    return "。".join(
        part
        for part in [
            _script_part(script_title) or "把自己还给自己的半日",
            f"真实场景会依次经过{'、'.join(spot_names)}" if spot_names else "",
            "每一幕都沿着真实点位展开，让情绪在路上慢慢放缓",
            "。".join(_script_part(line) for line in scene_lines if line),
        ]
        if part
    )


def generate_excel_script_sections(route, user_text="", intent=None, context=None):
    if not route:
        return []

    context = context or _script_context(route, user_text, intent)
    sections = []

    spots = route.get("spots", [])
    total_spots = len(spots)
    for index, spot in enumerate(spots, start=1):
        spot_name = _script_part(spot.get("name", ""))
        description = _script_part(spot.get("description", ""))
        keywords = "、".join(spot.get("feedback_keywords", []))
        paragraphs = _spot_script_paragraphs(
            spot_name=spot_name,
            description=description,
            keywords=keywords,
            index=index,
            total_spots=total_spots,
            context=context,
        )
        text = "\n\n".join(paragraphs)
        sections.append(
            {
                "type": "spot",
                "spot_id": str(spot.get("spot_id", "")).strip(),
                "spot_name": spot_name,
                "title": _spot_scene_title(index, spot_name, keywords, context),
                "text": text or "这一站适合放慢脚步，给路线留出一点停顿。",
                "paragraphs": paragraphs,
            }
        )
    return sections


def _script_context(route, user_text, intent):
    summary = _script_part((intent or {}).get("summary", ""))
    mood_source = summary or _script_part(user_text)
    matched_moods = [
        *route.get("matched_mindsets", []),
        *route.get("dominant_mindsets", []),
        *route.get("matched_tags", []),
    ]
    if not mood_source and matched_moods:
        mood_source = "、".join(str(mood).strip() for mood in matched_moods[:3] if str(mood).strip())
    mood = mood_source or _script_part(route.get("suitable_mood", "")) or "想让今天慢一点"
    start_emotion = mood[:28]
    end_emotion = _ending_emotion(route, mood)
    return {
        "mood": mood,
        "start_emotion": start_emotion,
        "end_emotion": end_emotion,
    }


def _script_title(route, context):
    route_text = _route_story_text(route, context)
    if any(word in route_text for word in ["天文", "海洋", "临港", "滴水湖"]):
        return "今天的脚步终于慢了下来"
    if any(word in route_text for word in ["武康", "梧桐"]):
        return "在梧桐影里慢慢静下来"
    if any(word in route_text for word in ["独处", "安静", "低噪音", "疗愈", "慢"]):
        return "把自己还给自己的半日"
    if any(word in route_text for word in ["夜景", "灯光", "外滩", "江", "浪漫"]):
        return "把今天交给灯光收好"
    if any(word in route_text for word in ["公园", "自然", "滨江", "松弛"]):
        return "逃离喧闹的三小时"
    if any(word in route_text for word in ["灵感", "艺术", "看展", "设计"]):
        return "让灵感重新亮起来"
    if any(word in route_text for word in ["怀旧", "老上海", "历史", "文学"]):
        return "和旧时光并肩慢走"
    if any(word in route_text for word in ["探索", "冷门", "隐藏", "工业"]):
        return "拐进城市隐藏的一页"
    return "一个人的城市低语"


def _first_paragraph(section):
    paragraphs = section.get("paragraphs")
    if isinstance(paragraphs, list):
        for paragraph in paragraphs:
            clean_paragraph = _script_part(paragraph)
            if clean_paragraph:
                return clean_paragraph
    text = _script_part(section.get("text", ""))
    return text.splitlines()[0].strip() if text else ""


def _spot_script_paragraphs(spot_name, description, keywords, index, total_spots, context):
    scene = _spot_scene_sentence(spot_name, description, keywords, index, total_spots)
    action = _spot_action_sentence(spot_name, index, total_spots, keywords, context)
    emotion = _emotion_stage(index, total_spots, context)

    paragraphs = [
        scene,
        f"如果不赶时间，{action}",
        f"也许走到这里的时候，你会发现真正放松下来的不是身体，而是一直紧绷着的注意力。{emotion}",
    ]
    return [paragraph for paragraph in paragraphs if paragraph]


def _spot_scene_title(index, spot_name, keywords, context):
    if "天文" in spot_name:
        scene_title = "宇宙仍在头顶。"
    elif "海昌" in spot_name or "海洋" in spot_name:
        scene_title = "海风把思绪放慢。"
    elif "滴水湖" in spot_name or spot_name.endswith("湖"):
        scene_title = "回到开阔的风里。"
    elif "武康" in spot_name or "梧桐" in keywords:
        scene_title = "树影先替你慢下来。"
    elif "外滩" in spot_name or "江" in spot_name:
        scene_title = "灯光把城市放远。"
    elif index == 1:
        scene_title = "从第一步开始降噪。"
    elif keywords:
        scene_title = f"顺着{keywords.split('、')[0]}继续往里走。"
    else:
        scene_title = "把脚步交给城市。"
    return f"{_section_number(index)}幕｜{scene_title}" if spot_name else f"{_section_number(index)}幕"


def _route_story_text(route, context):
    parts = [
        route.get("route_name", ""),
        route.get("route_intro_user_facing", ""),
        route.get("ai_script_angle", ""),
        route.get("match_reason", ""),
        route.get("suitable_mood", ""),
        " ".join(route.get("matched_mindsets", [])),
        " ".join(route.get("dominant_mindsets", [])),
        " ".join(route.get("matched_tags", [])),
        context.get("mood", "") if context else "",
    ]
    for spot in route.get("spots", []):
        parts.extend(
            [
                spot.get("name", ""),
                spot.get("description", ""),
                " ".join(spot.get("feedback_keywords", [])),
            ]
        )
    return " ".join(str(part or "") for part in parts)


def _spot_phrase(route, limit=None):
    names = [
        _script_part(spot.get("name", ""))
        for spot in route.get("spots", [])
        if _script_part(spot.get("name", ""))
    ]
    if limit:
        names = names[:limit]
    return "、".join(names)


def _spot_key(value):
    spot_id = _script_part(value.get("spot_id", ""))
    if spot_id:
        return f"id:{spot_id}"
    spot_name = _script_part(value.get("spot_name") or value.get("name"))
    if spot_name:
        return f"name:{spot_name}"
    return ""


def _ending_emotion(route, mood):
    route_text = " ".join(
        str(part or "")
        for part in [
            route.get("route_name", ""),
            route.get("ai_script_angle", ""),
            route.get("match_reason", ""),
            " ".join(route.get("matched_mindsets", [])),
            " ".join(route.get("matched_tags", [])),
            mood,
        ]
    )
    if any(word in route_text for word in ["夜景", "浪漫", "灯光"]):
        return "被城市灯光慢慢照亮"
    if any(word in route_text for word in ["灵感", "艺术", "看展", "设计"]):
        return "重新被灵感打开"
    if any(word in route_text for word in ["怀旧", "老上海", "历史", "文学"]):
        return "和城市旧时光轻轻相认"
    if any(word in route_text for word in ["探索", "冷门", "工业", "隐藏"]):
        return "对未知角落多一点好奇"
    if any(word in route_text for word in ["社交", "约会", "朋友"]):
        return "把关系里的温度放松下来"
    return "在真实街道里慢慢安静下来"


def _emotion_stage(index, total_spots, context):
    if total_spots <= 1 or index == 1:
        return f"先从{context['start_emotion']}里抽离一点，把注意力交给眼前的城市。"
    if index == total_spots:
        return f"走到这里，心情开始从游离变得清楚，靠近{context['end_emotion']}。"
    return "前一站留下的安静继续发酵，新的场景把情绪往更深处推了一步。"


def _spot_action_sentence(spot_name, index, total_spots, keywords, context):
    if index == 1:
        return f"在{spot_name or '这一站'}先停一会儿，只选一个细节观察，让身体比计划先到场。"
    if total_spots and index == total_spots:
        return f"在{spot_name or '最后一站'}放慢收尾，回想一路上哪个画面最贴近{context['mood']}。"
    if keywords:
        return f"在{spot_name or '这一站'}把脚步放轻，顺着{keywords}里最打动你的一个词继续走。"
    return f"在{spot_name or '这一站'}留出几分钟空白，不急着切换到下一处。"


def _spot_scene_sentence(spot_name, description, keywords, index, total_spots):
    name = spot_name or "这一站"
    detail = description or keywords
    if index == 1:
        lead = f"来到{name}的时候，今天的节奏先被按低了一点。"
    elif total_spots and index == total_spots:
        lead = f"到了{name}，前面几站留下的画面开始松开。"
    else:
        lead = f"从上一站离开以后，{name}把路线带向另一种声音。"

    if detail:
        return f"{lead}{detail}，会成为这一幕里最先浮出来的画面。"
    return f"{lead}城市在这里留下一点空白，让脚步有地方慢下来。"


def _script_part(value):
    return str(value or "").strip().rstrip("。；; ")


def _section_number(index):
    numbers = ["零", "第一", "第二", "第三", "第四", "第五", "第六", "第七", "第八", "第九", "第十"]
    if 0 < index < len(numbers):
        return numbers[index]
    return f"第{index}"


if __name__ == "__main__":
    app.run(debug=True)
