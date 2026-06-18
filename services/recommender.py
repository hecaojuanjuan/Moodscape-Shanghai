import copy
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTES_PATH = PROJECT_ROOT / "static" / "data" / "routes.json"
DEFAULT_TAGS_PATH = PROJECT_ROOT / "static" / "data" / "tags.json"


def load_routes(routes_path=DEFAULT_ROUTES_PATH):
    return _load_json(routes_path)


def load_tags(tags_path=DEFAULT_TAGS_PATH):
    return _load_json(tags_path)


def recommend_route(selected_tags=None, user_text="", routes_path=DEFAULT_ROUTES_PATH, tags_path=DEFAULT_TAGS_PATH):
    routes = load_routes(routes_path)
    tags = load_tags(tags_path)
    if not routes:
        return {}

    selected_tags = _normalize_selected_tags(selected_tags, tags)
    user_text = user_text if isinstance(user_text, str) else ""
    text_matched_tags = _match_tags_from_text(user_text, tags)

    scored_routes = []
    for index, route in enumerate(routes):
        score, matched_tags = _score_route(route, selected_tags, text_matched_tags, user_text)
        scored_routes.append((score, index, route, matched_tags))

    scored_routes.sort(key=lambda item: (-item[0], item[1]))
    best_score, _, best_route, matched_tags = scored_routes[0]

    result = copy.deepcopy(best_route)
    if best_score <= 0:
        result["matched_tags"] = []
        result["score"] = 0
        return result

    result["matched_tags"] = matched_tags
    result["score"] = min(best_score, 100)
    return result


def recommend_routes(selected_tags=None, user_text="", routes_path=DEFAULT_ROUTES_PATH, tags_path=DEFAULT_TAGS_PATH, limit=3):
    """兼容旧接口：旧版返回路线列表，新版核心逻辑只返回最佳路线。"""
    route = recommend_route(
        selected_tags=selected_tags,
        user_text=user_text,
        routes_path=routes_path,
        tags_path=tags_path,
    )
    return [route] if route else []


def _load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_selected_tags(selected_tags, tags):
    if not isinstance(selected_tags, list):
        return []

    button_to_emotion = {
        tag.get("user_button_text"): tag.get("emotion_tag")
        for tag in tags
        if tag.get("user_button_text") and tag.get("emotion_tag")
    }
    emotion_tags = {tag.get("emotion_tag") for tag in tags}

    normalized = []
    for raw_tag in selected_tags:
        if not isinstance(raw_tag, str):
            continue
        tag = raw_tag.strip()
        if not tag:
            continue
        if tag in emotion_tags:
            _append_unique(normalized, tag)
        elif tag in button_to_emotion:
            _append_unique(normalized, button_to_emotion[tag])
    return normalized


def _match_tags_from_text(user_text, tags):
    normalized_text = _normalize_text(user_text)
    if not normalized_text:
        return []

    matched_tags = []
    for tag in tags:
        emotion_tag = tag.get("emotion_tag")
        if not emotion_tag:
            continue
        keywords = _tag_keywords(tag)
        if any(_keyword_matches_text(keyword, normalized_text) for keyword in keywords):
            matched_tags.append(emotion_tag)
    return matched_tags


def _score_route(route, selected_tags, text_matched_tags, user_text):
    primary_tags = set(route.get("primary_emotion_tags", []))
    secondary_tags = set(route.get("secondary_emotion_tags", []))
    priority_map = route.get("tag_match_priority", {})
    matched_tags = []
    score = 0

    for tag in selected_tags:
        tag_score = _route_tag_score(tag, primary_tags, secondary_tags, priority_map, selected=True)
        if tag_score:
            score += tag_score
            _append_unique(matched_tags, tag)

    for tag in text_matched_tags:
        tag_score = _route_tag_score(tag, primary_tags, secondary_tags, priority_map, selected=False)
        if tag_score:
            score += tag_score
            _append_unique(matched_tags, tag)

    route_text = _route_search_text(route)
    for token in _tokenize_user_text(user_text):
        if token and token in route_text:
            score += 4

    return score, matched_tags


def _route_tag_score(tag, primary_tags, secondary_tags, priority_map, selected):
    score = 0
    if tag in primary_tags:
        score += 60 if selected else 36
    if tag in secondary_tags:
        score += 35 if selected else 22

    priority = priority_map.get(tag)
    if isinstance(priority, int):
        # Excel priority starts at 1. A smaller number means a stronger recommendation.
        score += max(10, 58 - priority * 8) if selected else max(5, 32 - priority * 5)
    return score


def _tag_keywords(tag):
    keywords = [
        tag.get("emotion_tag", ""),
        tag.get("user_button_text", ""),
        tag.get("user_state", ""),
        tag.get("experience_need", ""),
        tag.get("website_display_copy", ""),
        tag.get("ai_script_tone", ""),
    ]
    keywords.extend(tag.get("backend_scene_tags", []))
    keywords.extend(tag.get("example_spots", []))

    expanded = []
    for keyword in keywords:
        if not keyword:
            continue
        _append_unique(expanded, _normalize_text(keyword))
        for part in re.split(r"[\s,，。！？!?；;、/]+", str(keyword)):
            part = _normalize_text(part)
            if len(part) >= 2:
                _append_unique(expanded, part)
    return expanded


def _keyword_matches_text(keyword, normalized_text):
    if not keyword:
        return False
    return keyword in normalized_text or normalized_text in keyword


def _route_search_text(route):
    parts = [
        route.get("route_name", ""),
        route.get("reason", ""),
        route.get("route_intro_user_facing", ""),
        route.get("suitable_mood", ""),
        route.get("ai_script_angle", ""),
        " ".join(route.get("primary_emotion_tags", [])),
        " ".join(route.get("secondary_emotion_tags", [])),
        " ".join(route.get("backend_scene_tags", [])),
    ]
    for spot in route.get("spots", []):
        parts.append(spot.get("name", ""))
        parts.append(spot.get("description", ""))
        parts.append(" ".join(spot.get("emotion_tags", [])))
        parts.append(" ".join(spot.get("scene_tags", [])))
        parts.append(" ".join(spot.get("feedback_keywords", [])))
    return _normalize_text(" ".join(parts))


def _tokenize_user_text(user_text):
    if not isinstance(user_text, str):
        return []
    return [
        _normalize_text(token)
        for token in re.split(r"[\s,，。！？!?；;、/]+", user_text)
        if len(_normalize_text(token)) >= 2
    ]


def _normalize_text(value):
    return re.sub(r"\s+", "", str(value or "").lower())


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)
