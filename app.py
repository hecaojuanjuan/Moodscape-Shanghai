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
        if generated_script:
            route["script"] = generated_script["script"]
            route["script_sections"] = generated_script["script_sections"]
        else:
            route["script_sections"] = generate_excel_script_sections(route, user_text, intent)
            route["script"] = generate_excel_script(route, route["script_sections"])
        route["script_source"] = "qwen" if generated_script else "fallback"

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


def generate_excel_script(route, script_sections=None):
    if not route:
        return ""

    sections = script_sections or generate_excel_script_sections(route)
    spot_names = [
        section.get("spot_name", "")
        for section in sections
        if section.get("type") == "spot" and section.get("spot_name")
    ]
    emotion_turns = [
        _script_part(section.get("emotion_experience", ""))
        for section in sections
        if section.get("type") == "spot" and section.get("emotion_experience")
    ][:3]
    opening = next((section for section in sections if section.get("type") == "opening"), {})
    closing = next((section for section in reversed(sections) if section.get("type") == "closing"), {})

    return "。".join(
        part
        for part in [
            f"这是一条以你的情绪为主线的上海沉浸式剧本，从{_script_part(route.get('route_name', '这条路线'))}展开",
            _script_part(opening.get("text")),
            f"真实场景会依次经过{'、'.join(spot_names)}" if spot_names else "",
            f"情绪变化会从{'; '.join(emotion_turns)}慢慢推进" if emotion_turns else "",
            _script_part(closing.get("text")),
        ]
        if part
    )


def generate_excel_script_sections(route, user_text="", intent=None):
    if not route:
        return []

    route_name = _script_part(route.get("route_name", ""))
    route_intro = _script_part(route.get("route_intro_user_facing", ""))
    script_angle = _script_part(route.get("ai_script_angle", ""))
    match_reason = _script_part(route.get("match_reason", ""))
    context = _script_context(route, user_text, intent)
    opening_scene = (
        f"{route_name}像一段已经搭好的城市舞台，"
        f"{route_intro or script_angle or match_reason or '真实点位会把心情慢慢带入上海'}"
    )
    opening_text = "。".join(
        part
        for part in [
            f"这条路线不把你推进普通攻略，而是先接住此刻的心情：{context['mood']}",
            f"它会沿着{script_angle or route_name or '上海的真实点位'}展开，让情绪从{context['start_emotion']}走向{context['end_emotion']}",
            match_reason,
        ]
        if part
    )
    sections = [
        {
            "type": "opening",
            "title": "开场｜把心情交给这条路",
            "text": opening_text or "这条路线会把此刻的心情，慢慢带进上海的街道里。",
            "emotion_experience": f"从{context['start_emotion']}开始，不急着变好，先让自己被城市接住。",
            "action_guide": "先把这条路线当成一段预演，不急着打卡，也不用把每一站都完成得很漂亮。",
            "scene_image": opening_scene,
        }
    ]

    spots = route.get("spots", [])
    total_spots = len(spots)
    for index, spot in enumerate(spots, start=1):
        spot_name = _script_part(spot.get("name", ""))
        description = _script_part(spot.get("description", ""))
        keywords = "、".join(spot.get("feedback_keywords", []))
        emotion_stage = _emotion_stage(index, total_spots, context)
        action = _spot_action_guide(spot_name, index, total_spots, keywords, context)
        scene = _spot_scene_image(spot_name, description, keywords)
        text = "。".join(
            part
            for part in [
                f"这一幕发生在{spot_name}" if spot_name else "",
                emotion_stage,
                f"你可以{action}",
                scene,
            ]
            if part
        )
        sections.append(
            {
                "type": "spot",
                "spot_id": str(spot.get("spot_id", "")).strip(),
                "spot_name": spot_name,
                "title": f"{_section_number(index)}幕｜{spot_name}" if spot_name else f"{_section_number(index)}幕",
                "text": text or "这一站适合放慢脚步，给路线留出一点停顿。",
                "emotion_experience": emotion_stage,
                "action_guide": action,
                "scene_image": scene,
            }
        )

    spot_names = [
        _script_part(spot.get("name", ""))
        for spot in spots
        if _script_part(spot.get("name", ""))
    ]
    closing_scene = (
        f"{'、'.join(spot_names)}会在回望时连成一条清晰的上海线索。"
        if spot_names
        else "这些真实点位会在回望时连成一条清晰的上海线索。"
    )
    sections.append(
        {
            "type": "closing",
            "title": "收束｜把变化带回自己",
            "text": f"走完这些点位后，路线不会只留下到此一游的清单，而会把{context['mood']}收束成一段更清楚的城市记忆。",
            "emotion_experience": f"从{context['start_emotion']}走到{context['end_emotion']}，不是被治好，而是多了一点可以安放自己的空间。",
            "action_guide": "离开前选一个最有感觉的画面记下来，它会成为这段路线真正的结尾。",
            "scene_image": closing_scene,
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


def _spot_action_guide(spot_name, index, total_spots, keywords, context):
    if index == 1:
        return f"在{spot_name or '这一站'}先停一会儿，只选一个细节观察，让身体比计划先到场。"
    if total_spots and index == total_spots:
        return f"在{spot_name or '最后一站'}放慢收尾，回想一路上哪个画面最贴近{context['mood']}。"
    if keywords:
        return f"在{spot_name or '这一站'}把脚步放轻，顺着{keywords}里最打动你的一个词继续走。"
    return f"在{spot_name or '这一站'}留出几分钟空白，不急着切换到下一处。"


def _spot_scene_image(spot_name, description, keywords):
    if description and keywords:
        return f"{spot_name}像这一幕的真实布景，{description}；{keywords}会成为画面里的细节。"
    if description:
        return f"{spot_name}像这一幕的真实布景，{description}。"
    if keywords:
        return f"{spot_name or '这一站'}由{keywords}组成，像一格慢慢显影的城市画面。"
    return f"{spot_name or '这一站'}给这条路线留下一处可以停顿的城市画面。"


def _script_part(value):
    return str(value or "").strip().rstrip("。；; ")


def _section_number(index):
    numbers = ["零", "第一", "第二", "第三", "第四", "第五", "第六", "第七", "第八", "第九", "第十"]
    if 0 < index < len(numbers):
        return numbers[index]
    return f"第{index}"


if __name__ == "__main__":
    app.run(debug=True)
