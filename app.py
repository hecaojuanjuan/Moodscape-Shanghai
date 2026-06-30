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
        uses_qwen_script = _script_payload_is_complete(generated_script)
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
    "script_opening",
    "script_role",
    "script_sensory",
    "script_closing",
)


def _apply_script_payload(route, script_payload):
    for key in SCRIPT_PAYLOAD_KEYS:
        route[key] = script_payload.get(key, {} if key == "script_sensory" else ([] if key == "script_sections" else ""))


def _script_payload_is_complete(script_payload):
    if not isinstance(script_payload, dict):
        return False
    sensory = script_payload.get("script_sensory")
    return all(
        [
            script_payload.get("script"),
            script_payload.get("script_sections"),
            script_payload.get("script_title"),
            script_payload.get("script_opening"),
            script_payload.get("script_role"),
            isinstance(sensory, dict),
            all(sensory.get(key) for key in ("see", "hear", "smell", "do")) if isinstance(sensory, dict) else False,
            script_payload.get("script_closing"),
        ]
    )


def generate_excel_script_payload(route, user_text="", intent=None):
    if not route:
        return {
            "script": "",
            "script_sections": [],
            "script_title": "",
            "script_opening": "",
            "script_role": "",
            "script_sensory": {"see": "", "hear": "", "smell": "", "do": ""},
            "script_closing": "",
        }

    context = _script_context(route, user_text, intent)
    sections = generate_excel_script_sections(route, user_text, intent, context=context)
    script_title = _script_title(route, context)
    script_opening = _script_opening(route, context)
    script_role = _script_role(context)
    script_sensory = _script_sensory(route, context)
    script_closing = _script_closing(route, context)
    script = generate_excel_script(
        route,
        sections,
        script_title=script_title,
        script_opening=script_opening,
        script_role=script_role,
        script_closing=script_closing,
    )
    return {
        "script": script,
        "script_sections": sections,
        "script_title": script_title,
        "script_opening": script_opening,
        "script_role": script_role,
        "script_sensory": script_sensory,
        "script_closing": script_closing,
    }


def generate_excel_script(
    route,
    script_sections=None,
    script_title="",
    script_opening="",
    script_role="",
    script_closing="",
):
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
            _script_part(script_title) or "把自己还给自己的半日",
            _script_part(script_opening) or _script_part(opening.get("text")),
            _script_part(script_role),
            f"真实场景会依次经过{'、'.join(spot_names)}" if spot_names else "",
            f"情绪变化会从{'; '.join(emotion_turns)}慢慢推进" if emotion_turns else "",
            _script_part(script_closing) or _script_part(closing.get("text")),
        ]
        if part
    )


def generate_excel_script_sections(route, user_text="", intent=None, context=None):
    if not route:
        return []

    route_name = _script_part(route.get("route_name", ""))
    route_intro = _script_part(route.get("route_intro_user_facing", ""))
    script_angle = _script_part(route.get("ai_script_angle", ""))
    match_reason = _script_part(route.get("match_reason", ""))
    context = context or _script_context(route, user_text, intent)
    opening_scene = (
        f"{route_name}像一段已经搭好的城市舞台，"
        f"{route_intro or script_angle or match_reason or '真实点位会把心情慢慢带入上海'}"
    )
    opening_text = _script_opening(route, context)
    sections = [
        {
            "type": "opening",
            "title": "开场白｜把心情交给这条路",
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
        experience = _spot_experience(spot_name, keywords, context)
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
                "location": spot_name,
                "title": _spot_scene_title(index, spot_name, keywords, context),
                "text": text or "这一站适合放慢脚步，给路线留出一点停顿。",
                "experience": experience,
                "emotion_shift": emotion_stage,
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
            "title": "结尾收束｜把变化带回自己",
            "text": _script_closing(route, context),
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


def _script_title(route, context):
    route_text = _route_story_text(route, context)
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


def _script_opening(route, context):
    script_angle = _script_part(route.get("ai_script_angle", ""))
    match_reason = _script_part(route.get("match_reason", ""))
    spot_phrase = _spot_phrase(route, limit=3)
    route_scene = script_angle or spot_phrase or "这几处真实的上海点位"
    why = (
        f"它不会把你推向热闹的人群，而是沿着{route_scene}慢慢展开"
        if route_scene
        else "它不会把你推向热闹的人群，而是让城市节奏先慢下来"
    )
    if spot_phrase:
        why = f"{why}，带你经过{spot_phrase}"
    return "。".join(
        part
        for part in [
            f"如果今天的你带着{context['mood']}，这条路线适合你",
            why,
            f"它的作用不是安排你完成什么，而是让情绪从{context['start_emotion']}慢慢走向{context['end_emotion']}",
            match_reason,
        ]
        if part
    )


def _script_role(context):
    return (
        f"今天的你是今天的主角，也是一位短暂逃离日常的人。"
        f"你不需要完成任务，不需要证明自己来过，只需要跟着城市的节奏慢一点，"
        f"让{context['mood']}在路上有地方停靠。"
    )


def _script_sensory(route, context):
    route_text = _route_story_text(route, context)
    spot_phrase = _spot_phrase(route, limit=2)
    if any(word in route_text for word in ["夜景", "灯光", "外滩", "江", "滨江"]):
        see = f"街灯、建筑轮廓、江面反光，以及{spot_phrase or '真实点位'}之间逐渐铺开的夜色。"
        hear = "脚步声、远处车流、江边风声，以及人群被拉远后的城市底噪。"
        smell = "潮湿空气、江风、雨后路面和街边植物的气息。"
    elif any(word in route_text for word in ["艺术", "看展", "设计", "灵感"]):
        see = f"展陈空间、建筑线条、橱窗细节，以及{spot_phrase or '每一处点位'}里的光影变化。"
        hear = "压低的说话声、脚步声、门被轻轻推开的声音。"
        smell = "纸张、木质空间、咖啡和室内空气里安静的味道。"
    elif any(word in route_text for word in ["公园", "自然", "植物", "松江", "滨水"]):
        see = f"植物、开阔的路面、河面或草木边缘，以及{spot_phrase or '真实点位'}里的留白。"
        hear = "风声、脚步声、偶尔经过的车流声和更远处的日常声响。"
        smell = "植物、泥土、雨后路面和微湿空气的味道。"
    else:
        see = f"树影、建筑轮廓、街角橱窗，以及{spot_phrase or '真实点位'}里慢慢显影的城市画面。"
        hear = "脚步声、风声、远处车流，偶尔还有咖啡机或店门开合的声音。"
        smell = "咖啡香、雨后路面、植物和老街区空气里温和的味道。"

    if any(word in route_text for word in ["看展", "艺术", "设计"]):
        do = "慢走、看展、停留、拍下一个细节，再写下一句突然冒出来的话。"
    elif any(word in route_text for word in ["夜景", "灯光", "江"]):
        do = "慢走、停在光线好看的地方、拍照、听一首歌，然后让视线在远处停一会儿。"
    else:
        do = "慢走、停留、拍低饱和照片、写字、听歌，或者什么也不做地发呆。"
    return {"see": see, "hear": hear, "smell": smell, "do": do}


def _script_closing(route, context):
    spot_phrase = _spot_phrase(route, limit=3)
    route_memory = f"走过{spot_phrase}之后，" if spot_phrase else "走完这条路线之后，"
    return (
        f"情绪落点：这条路线不会让你立刻变得开心，也不会把今天变成一份攻略成果。"
        f"{route_memory}你会把{context['mood']}慢慢收进一段更清楚的城市记忆里。"
        f"独处不是被世界落下，而是终于能听见自己从{context['start_emotion']}走向{context['end_emotion']}。"
    )


def _spot_experience(spot_name, keywords, context):
    if keywords:
        return f"慢走、停留，顺着{keywords}里最打动你的细节拍照、写字或发呆。"
    return f"在{spot_name or '这一站'}慢走、停留、拍一张低饱和照片，给自己几分钟空白。"


def _spot_scene_title(index, spot_name, keywords, context):
    if index == 1:
        scene_title = "从街角开始降噪"
    elif index >= 1 and keywords:
        scene_title = f"顺着{keywords.split('、')[0]}继续往里走"
    else:
        scene_title = "把脚步交给城市"
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
