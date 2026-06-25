import copy
import re

from services.dynamic_routes import build_dynamic_routes, distance_km
from services.excel_data import load_excel_data
from services.profile_vector import (
    build_route_profile_vector,
    build_user_profile_vector,
    cosine_similarity,
    matched_profile_traits,
)


SELECTED_MAPPING_BASE = 500
TEXT_MAPPING_BASE = 320
SELECTED_PRIORITY_STEP = 40
TEXT_PRIORITY_STEP = 26
SELECTED_PRIMARY_TAG_BONUS = 45
SELECTED_SECONDARY_TAG_BONUS = 26
TEXT_PRIMARY_TAG_BONUS = 28
TEXT_SECONDARY_TAG_BONUS = 16
BEST_MAPPING_PRIORITY = 1
MINDSET_MAX_SCORE = 100
SELECTED_MINDSET_WEIGHT = 1.15
TEXT_MINDSET_WEIGHT = 0.65
TOKEN_MATCH_SCORE = 4
PROFILE_SIMILARITY_SCORE = 180
MATCH_PERCENT_CAP = 98


def load_routes():
    return copy.deepcopy(load_excel_data()["routes"])


def load_tags():
    return copy.deepcopy(load_excel_data()["tags"])


def load_mindset_tags():
    return list(load_excel_data()["mindset_tags"])


def recommend_route(
    selected_tags=None,
    user_text="",
    profile_answers=None,
    inferred_experience_tags=None,
    inferred_mindset_tags=None,
    limit=3,
):
    routes = recommend_routes(
        selected_tags=selected_tags,
        user_text=user_text,
        profile_answers=profile_answers,
        inferred_experience_tags=inferred_experience_tags,
        inferred_mindset_tags=inferred_mindset_tags,
        limit=limit,
    )
    return routes[0] if routes else {}


def recommend_routes(
    selected_tags=None,
    user_text="",
    profile_answers=None,
    inferred_experience_tags=None,
    inferred_mindset_tags=None,
    limit=3,
):
    data = load_excel_data()
    selected = _normalize_selected_tags(selected_tags)
    user_text = user_text if isinstance(user_text, str) else ""
    inferred_experience_tags = _normalize_inferred_tags(
        inferred_experience_tags,
        {tag["emotion_tag"] for tag in data["tags"]},
    )
    inferred_mindset_tags = _normalize_inferred_tags(
        inferred_mindset_tags,
        set(data["mindset_tags"]),
    )
    if not selected and not user_text.strip() and not inferred_experience_tags and not inferred_mindset_tags:
        return []

    selected_experience_tags, selected_mindsets = _split_selected_tags(selected, data)
    text_matched_tags = _match_tags_from_text(user_text, data)
    text_matched_mindsets = _match_mindsets_from_text(user_text, text_matched_tags, data)
    text_matched_tags = _merge_inferred_tags(
        text_matched_tags,
        inferred_experience_tags,
        selected_experience_tags,
    )
    text_matched_mindsets = _merge_inferred_tags(
        text_matched_mindsets,
        inferred_mindset_tags,
        selected_mindsets,
    )
    user_profile = build_user_profile_vector(profile_answers)
    possible_score = _query_possible_score(
        selected_experience_tags,
        selected_mindsets,
        text_matched_tags,
        text_matched_mindsets,
        user_text,
        bool(user_profile["vector"]),
    )

    seed_routes = _recommend_seed_routes(
        data,
        selected_experience_tags,
        selected_mindsets,
        text_matched_tags,
        text_matched_mindsets,
        user_text,
        user_profile,
        possible_score,
        limit,
    )
    if not seed_routes:
        return []

    dynamic_routes = build_dynamic_routes(
        data=data,
        seed_routes=seed_routes,
        selected_tags=selected_experience_tags,
        selected_mindsets=selected_mindsets,
        text_tags=text_matched_tags,
        text_mindsets=text_matched_mindsets,
        user_text=user_text,
        user_profile=user_profile,
        possible_score=possible_score,
        match_percent=_match_percent,
        limit=limit,
    )
    return dynamic_routes or seed_routes


def _recommend_seed_routes(
    data,
    selected_experience_tags,
    selected_mindsets,
    text_matched_tags,
    text_matched_mindsets,
    user_text,
    user_profile,
    possible_score,
    limit,
):
    scored = []
    for index, route in enumerate(data["routes"]):
        (
            raw_score,
            matched_tags,
            matched_mindsets,
            reason,
            card_copy,
            profile_similarity,
            profile_traits,
        ) = _score_route(
            route,
            selected_experience_tags,
            selected_mindsets,
            text_matched_tags,
            text_matched_mindsets,
            user_text,
            data,
            user_profile,
        )
        scored.append(
            {
                "raw_score": raw_score,
                "match_percent": _match_percent(raw_score, possible_score),
                "index": index,
                "route": route,
                "matched_tags": matched_tags,
                "matched_mindsets": matched_mindsets,
                "match_reason": reason,
                "suggested_card_copy": card_copy,
                "profile_similarity": profile_similarity,
                "matched_profile_traits": profile_traits,
            }
        )

    scored.sort(key=lambda item: (-item["match_percent"], -item["raw_score"], item["index"]))
    candidates = scored[: max(1, limit)]
    return _format_candidates(candidates, possible_score)


def _normalize_selected_tags(selected_tags):
    if not isinstance(selected_tags, list):
        return []
    normalized = []
    for tag in selected_tags:
        if isinstance(tag, str) and tag.strip() and tag.strip() not in normalized:
            normalized.append(tag.strip())
    return normalized


def _normalize_inferred_tags(inferred_tags, allowed_tags):
    if not isinstance(inferred_tags, list):
        return []
    normalized = []
    for tag in inferred_tags:
        if isinstance(tag, str):
            clean_tag = tag.strip()
            if clean_tag in allowed_tags and clean_tag not in normalized:
                normalized.append(clean_tag)
    return normalized


def _merge_inferred_tags(text_tags, inferred_tags, selected_tags):
    merged = list(text_tags)
    selected = set(selected_tags)
    for tag in inferred_tags:
        if tag not in selected:
            _append_unique(merged, tag)
    return merged


def _split_selected_tags(selected, data):
    button_to_emotion = {
        tag["user_button_text"]: tag["emotion_tag"]
        for tag in data["tags"]
        if tag["user_button_text"] and tag["emotion_tag"]
    }
    emotion_tags = {tag["emotion_tag"] for tag in data["tags"]}
    mindset_tags = set(data["mindset_tags"])

    experience_tags = []
    mindsets = []
    for tag in selected:
        if tag in emotion_tags:
            _append_unique(experience_tags, tag)
        elif tag in button_to_emotion:
            _append_unique(experience_tags, button_to_emotion[tag])
        elif tag in mindset_tags:
            _append_unique(mindsets, tag)
    return experience_tags, mindsets


def _match_tags_from_text(user_text, data):
    normalized_text = _normalize_text(user_text)
    if not normalized_text:
        return []

    matched = []
    for tag in data["tags"]:
        tag_text = _search_text(
            tag["emotion_tag"],
            tag["user_button_text"],
            tag["user_state"],
            tag["experience_need"],
            tag["website_display_copy"],
            tag["ai_script_tone"],
            *tag["backend_scene_tags"],
            *tag["example_spots"],
        )
        if _text_matches(normalized_text, tag_text):
            _append_unique(matched, tag["emotion_tag"])
    return matched


def _match_mindsets_from_text(user_text, text_matched_tags, data):
    normalized_text = _normalize_text(user_text)
    mindset_tags = data["mindset_tags"]
    matched = []

    for mindset in mindset_tags:
        if mindset and _normalize_text(mindset) in normalized_text:
            _append_unique(matched, mindset)

    tags_by_name = {tag["emotion_tag"]: tag for tag in data["tags"]}
    for tag_name in text_matched_tags:
        tag = tags_by_name.get(tag_name)
        if not tag:
            continue
        for scene_tag in tag["backend_scene_tags"]:
            if scene_tag in mindset_tags:
                _append_unique(matched, scene_tag)
        for mindset in mindset_tags:
            if _normalize_text(mindset) and _normalize_text(mindset) in _search_text(tag_name, tag["experience_need"], tag["website_display_copy"]):
                _append_unique(matched, mindset)
    return matched


def _score_route(route, selected_tags, selected_mindsets, text_tags, text_mindsets, user_text, data, user_profile):
    matched_tags = []
    matched_mindsets = []
    reasons = []
    card_copies = []
    score = 0.0
    profile_similarity = 0
    profile_traits = []

    mapping_by_pair = {
        (mapping["emotion_tag"], mapping["route_id"]): mapping
        for mapping in data["mappings"]
    }

    for tag in selected_tags:
        tag_score, mapping = _experience_tag_score(route, tag, mapping_by_pair, selected=True)
        if tag_score:
            score += tag_score
            _append_unique(matched_tags, tag)
            if mapping:
                _append_unique(reasons, mapping["match_reason"])
                _append_unique(card_copies, mapping["suggested_card_copy"])

    for tag in text_tags:
        tag_score, mapping = _experience_tag_score(route, tag, mapping_by_pair, selected=False)
        if tag_score:
            score += tag_score
            _append_unique(matched_tags, tag)
            if mapping:
                _append_unique(reasons, mapping["match_reason"])
                _append_unique(card_copies, mapping["suggested_card_copy"])

    for mindset in selected_mindsets:
        mindset_score = _mindset_score(route, mindset, selected=True)
        if mindset_score:
            score += mindset_score
            _append_unique(matched_mindsets, mindset)

    for mindset in text_mindsets:
        mindset_score = _mindset_score(route, mindset, selected=False)
        if mindset_score:
            score += mindset_score
            _append_unique(matched_mindsets, mindset)

    route_text = _route_search_text(route)
    for token in _input_tokens(user_text):
        if token in route_text:
            score += TOKEN_MATCH_SCORE

    if user_profile["vector"]:
        route_vector = build_route_profile_vector(route)
        profile_similarity = cosine_similarity(user_profile["vector"], route_vector)
        if profile_similarity:
            score += profile_similarity * PROFILE_SIMILARITY_SCORE
            profile_traits = matched_profile_traits(user_profile, route_vector)

    reason = next((reason for reason in reasons if reason), "") or route["route_intro_user_facing"] or route["suitable_mood"] or route["ai_script_angle"]
    card_copy = next((copy_text for copy_text in card_copies if copy_text), "") or route["route_intro_user_facing"]
    return score, matched_tags, matched_mindsets, reason, card_copy, profile_similarity, profile_traits


def _experience_tag_score(route, tag, mapping_by_pair, selected):
    mapping = mapping_by_pair.get((tag, route["route_id"]))
    score = 0.0
    if mapping:
        priority = mapping["priority"] or 9
        base = SELECTED_MAPPING_BASE if selected else TEXT_MAPPING_BASE
        step = SELECTED_PRIORITY_STEP if selected else TEXT_PRIORITY_STEP
        score += base - priority * step
    if tag in route["primary_emotion_tags"]:
        score += SELECTED_PRIMARY_TAG_BONUS if selected else TEXT_PRIMARY_TAG_BONUS
    if tag in route["secondary_emotion_tags"]:
        score += SELECTED_SECONDARY_TAG_BONUS if selected else TEXT_SECONDARY_TAG_BONUS
    return max(score, 0), mapping


def _mindset_score(route, mindset, selected):
    value = route["mindset_scores"].get(mindset, 0)
    if not value:
        return 0
    return value * (SELECTED_MINDSET_WEIGHT if selected else TEXT_MINDSET_WEIGHT)


def _query_possible_score(selected_tags, selected_mindsets, text_tags, text_mindsets, user_text, has_profile):
    score = 0.0
    for _ in selected_tags:
        score += _experience_tag_possible_score(selected=True)
    for _ in text_tags:
        score += _experience_tag_possible_score(selected=False)
    for _ in selected_mindsets:
        score += MINDSET_MAX_SCORE * SELECTED_MINDSET_WEIGHT
    for _ in text_mindsets:
        score += MINDSET_MAX_SCORE * TEXT_MINDSET_WEIGHT
    score += len(_input_tokens(user_text)) * TOKEN_MATCH_SCORE
    if has_profile:
        score += PROFILE_SIMILARITY_SCORE
    return score


def _experience_tag_possible_score(selected):
    if selected:
        return (
            SELECTED_MAPPING_BASE
            - BEST_MAPPING_PRIORITY * SELECTED_PRIORITY_STEP
            + SELECTED_PRIMARY_TAG_BONUS
            + SELECTED_SECONDARY_TAG_BONUS
        )
    return (
        TEXT_MAPPING_BASE
        - BEST_MAPPING_PRIORITY * TEXT_PRIORITY_STEP
        + TEXT_PRIMARY_TAG_BONUS
        + TEXT_SECONDARY_TAG_BONUS
    )


def _format_candidates(candidates, possible_score):
    formatted = []
    for item in candidates:
        route = copy.deepcopy(item["route"])
        route["raw_score"] = round(item["raw_score"], 2)
        route["possible_score"] = round(possible_score, 2)
        route["score"] = route["raw_score"]
        route["match_percent"] = item["match_percent"]
        route["matched_tags"] = item["matched_tags"]
        route["matched_mindsets"] = item["matched_mindsets"]
        route["match_reason"] = item["match_reason"]
        route["suggested_card_copy"] = item["suggested_card_copy"]
        route["profile_similarity"] = round(item["profile_similarity"], 3)
        route["matched_profile_traits"] = item["matched_profile_traits"]
        route["is_dynamic"] = False
        route["source_route_ids"] = [route["route_id"]]
        route["route_distance_km"] = round(_route_distance_km(route.get("spots", [])), 2)
        formatted.append(route)
    return formatted


def _match_percent(score, possible_score):
    if possible_score <= 0:
        return 0
    percent = score / possible_score * 100
    return round(max(0, min(MATCH_PERCENT_CAP, percent)), 1)


def _route_search_text(route):
    parts = [
        route["route_name"],
        route["route_intro_user_facing"],
        route["suitable_mood"],
        route["ai_script_angle"],
        route["route_spots"],
        *route["primary_emotion_tags"],
        *route["secondary_emotion_tags"],
        *route["backend_scene_tags"],
    ]
    for spot in route["spots"]:
        parts.extend(
            [
                spot["name"],
                spot["description"],
                spot["district"],
                spot["open_time"],
                spot["ticket_reservation"],
                spot["address"],
                spot["source_note"],
                spot["update_note"],
                *spot["emotion_tags"],
                *spot["scene_tags"],
                *spot["feedback_keywords"],
            ]
        )
    return _search_text(*parts)


def _route_distance_km(spots):
    return sum(distance_km(left, right) for left, right in zip(spots, spots[1:]))


def _input_tokens(user_text):
    return [
        _normalize_text(token)
        for token in re.split(r"[\s,，。！？!?；;、/]+", str(user_text or ""))
        if len(_normalize_text(token)) >= 2
    ]


def _search_text(*parts):
    return _normalize_text(" ".join(str(part or "") for part in parts))


def _text_matches(normalized_text, source_text):
    if not normalized_text or not source_text:
        return False
    if normalized_text in source_text or source_text in normalized_text:
        return True
    return any(token and token in source_text for token in _input_tokens(normalized_text))


def _normalize_text(value):
    return re.sub(r"[\s,，。！？!?；;、/]+", "", str(value or "").lower())


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)
