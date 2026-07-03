import re


LIST_FIELDS = (
    "inferred_tags",
    "preferred_scene_types",
    "avoid_scene_types",
    "must_have",
    "soft_preferences",
    "route_keywords",
)

BUDGET_VALUES = {"low", "medium", "high", "unknown"}
CROWD_VALUES = {"quiet", "lively", "balanced", "unknown"}
TIME_VALUES = {"day", "night", "flexible", "unknown"}


def fallback_intent(selected_tags=None, mood_text="", available_tags=None):
    allowed = set(available_tags or [])
    inferred_tags = []
    for tag in selected_tags or []:
        clean_tag = _clean_text(tag)
        if clean_tag and (not allowed or clean_tag in allowed) and clean_tag not in inferred_tags:
            inferred_tags.append(clean_tag)

    normalized_intent = _clean_text(mood_text)
    if not normalized_intent and inferred_tags:
        normalized_intent = "、".join(inferred_tags)

    intent = {
        "normalized_intent": normalized_intent,
        "inferred_tags": inferred_tags,
        "preferred_scene_types": [],
        "avoid_scene_types": [],
        "must_have": [],
        "soft_preferences": [],
        "route_keywords": [],
        "mood_tone": "",
        "budget_preference": "unknown",
        "crowd_preference": "unknown",
        "time_preference": "unknown",
        "confidence": 0,
        "source": "fallback",
    }
    return _with_summary(intent)


def normalize_intent(raw_intent, selected_tags=None, mood_text="", available_tags=None, source="qwen"):
    raw = raw_intent if isinstance(raw_intent, dict) else {}
    available = set(available_tags or [])
    intent = fallback_intent(selected_tags, mood_text, available_tags)
    intent["source"] = source

    normalized_intent = _clean_text(raw.get("normalized_intent") or raw.get("summary"))
    if normalized_intent:
        intent["normalized_intent"] = normalized_intent[:120]

    for field in LIST_FIELDS:
        if field not in raw or not isinstance(raw.get(field), list):
            continue
        values = _clean_list(raw.get(field))
        if field == "inferred_tags":
            values = [value for value in values if not available or value in available]
        intent[field] = values

    intent["mood_tone"] = _clean_text(raw.get("mood_tone"))[:40]
    intent["budget_preference"] = _enum_value(raw.get("budget_preference"), BUDGET_VALUES)
    intent["crowd_preference"] = _enum_value(raw.get("crowd_preference"), CROWD_VALUES)
    intent["time_preference"] = _enum_value(raw.get("time_preference"), TIME_VALUES)
    intent["confidence"] = _confidence(raw.get("confidence"))
    return _with_summary(intent)


def add_legacy_intent_tags(intent, experience_tags, mindset_tags):
    normalized = dict(intent or {})
    inferred_tags = _clean_list(normalized.get("inferred_tags"))
    experience = list(normalized.get("inferred_experience_tags") or [])
    mindset = list(normalized.get("inferred_mindset_tags") or [])
    experience_allowed = set(experience_tags or [])
    mindset_allowed = set(mindset_tags or [])

    for tag in inferred_tags:
        if tag in experience_allowed and tag not in experience:
            experience.append(tag)
        if tag in mindset_allowed and tag not in mindset:
            mindset.append(tag)

    normalized["inferred_experience_tags"] = [
        tag for tag in experience if isinstance(tag, str) and tag in experience_allowed
    ]
    normalized["inferred_mindset_tags"] = [
        tag for tag in mindset if isinstance(tag, str) and tag in mindset_allowed
    ]
    return _with_summary(normalized)


def build_route_summaries(routes):
    summaries = []
    for route in routes or []:
        if not isinstance(route, dict) or not route.get("route_id"):
            continue
        summaries.append(
            {
                "route_id": route.get("route_id", ""),
                "route_name": route.get("route_name", ""),
                "route_tags": _unique(
                    list(route.get("primary_emotion_tags") or [])
                    + list(route.get("secondary_emotion_tags") or [])
                    + list(route.get("dominant_mindsets") or [])
                ),
                "description": _join_text(
                    route.get("route_intro_user_facing"),
                    route.get("suitable_mood"),
                    route.get("ai_script_angle"),
                )[:260],
                "scene_tags": list(route.get("backend_scene_tags") or []),
                "spot_summaries": [
                    {
                        "spot_id": spot.get("spot_id", ""),
                        "name": spot.get("name", ""),
                        "scene_tags": list(spot.get("scene_tags") or [])[:4],
                        "keywords": list(spot.get("feedback_keywords") or [])[:4],
                    }
                    for spot in (route.get("spots") or [])[:2]
                    if isinstance(spot, dict)
                ],
            }
        )
    return summaries


def score_route_for_intent(route, route_spots, selected_tags, intent, mood_text=""):
    if not isinstance(route, dict):
        return 0, False, False, []

    route_text = _route_text(route)
    spots_text = _spots_text(route_spots or route.get("spots") or [])
    score = 0
    selected_hit = False
    intent_hit = False
    matched_terms = []
    has_mood = bool(_clean_text(mood_text) or _clean_text((intent or {}).get("normalized_intent")))

    for tag in selected_tags or []:
        if _contains_term(route_text, tag):
            score += 10
            selected_hit = True
            _append_unique(matched_terms, tag)

    for tag in _clean_list((intent or {}).get("inferred_tags")):
        if _contains_term(route_text, tag):
            score += 7
            if has_mood:
                intent_hit = True
            _append_unique(matched_terms, tag)

    for item in _clean_list((intent or {}).get("preferred_scene_types")):
        if _contains_term(route_text, item):
            score += 6
            intent_hit = True
            _append_unique(matched_terms, item)
        if _contains_term(spots_text, item):
            score += 4
            intent_hit = True
            _append_unique(matched_terms, item)

    for keyword in _clean_list((intent or {}).get("route_keywords")):
        if _contains_term(route_text, keyword):
            score += 5
            intent_hit = True
            _append_unique(matched_terms, keyword)
        if _contains_term(spots_text, keyword):
            score += 4
            intent_hit = True
            _append_unique(matched_terms, keyword)

    for item in _clean_list((intent or {}).get("must_have")):
        if _contains_term(route_text, item) or _contains_term(spots_text, item):
            score += 8
            intent_hit = True
            _append_unique(matched_terms, item)

    for item in _clean_list((intent or {}).get("soft_preferences")):
        if _contains_term(route_text, item) or _contains_term(spots_text, item):
            score += 4
            intent_hit = True
            _append_unique(matched_terms, item)

    for item in _clean_list((intent or {}).get("avoid_scene_types")):
        if _contains_term(route_text, item) or _contains_term(spots_text, item):
            score -= 5
            _append_unique(matched_terms, f"避开:{item}")

    if selected_hit and intent_hit and has_mood:
        score += 8

    return score, selected_hit, intent_hit, matched_terms


def score_spot_for_intent(spot, selected_tags, intent, candidate_route_ids=None):
    if not isinstance(spot, dict):
        return 0

    candidate_route_ids = set(candidate_route_ids or [])
    spot_text = _spot_text(spot)
    score = 0

    if spot.get("route_id") in candidate_route_ids:
        score += 5

    for tag in selected_tags or []:
        if _contains_term(spot_text, tag):
            score += 5

    for tag in _clean_list((intent or {}).get("inferred_tags")):
        if _contains_term(spot_text, tag):
            score += 4

    for item in _clean_list((intent or {}).get("preferred_scene_types")):
        if _contains_term(spot_text, item):
            score += 5

    for keyword in _clean_list((intent or {}).get("route_keywords")):
        if _contains_term(spot_text, keyword):
            score += 4

    for item in _clean_list((intent or {}).get("must_have")):
        if _contains_term(spot_text, item):
            score += 8

    for item in _clean_list((intent or {}).get("avoid_scene_types")):
        if _contains_term(spot_text, item):
            score -= 5

    return score


def intent_has_matching_signal(intent):
    if not isinstance(intent, dict):
        return False
    return any(_clean_list(intent.get(field)) for field in LIST_FIELDS)


def _with_summary(intent):
    normalized_intent = _clean_text(intent.get("normalized_intent")) or _clean_text(intent.get("summary"))
    intent["normalized_intent"] = normalized_intent
    intent["summary"] = normalized_intent[:80]
    intent.setdefault("inferred_experience_tags", [])
    intent.setdefault("inferred_mindset_tags", [])
    return intent


def _route_text(route):
    return _normalize_text(
        _join_text(
            route.get("route_name"),
            route.get("route_intro_user_facing"),
            route.get("suitable_mood"),
            route.get("ai_script_angle"),
            route.get("route_spots"),
            route.get("budget_level"),
            *(route.get("primary_emotion_tags") or []),
            *(route.get("secondary_emotion_tags") or []),
            *(route.get("backend_scene_tags") or []),
            *(route.get("dominant_mindsets") or []),
        )
    )


def _spots_text(spots):
    return _normalize_text(" ".join(_spot_text(spot) for spot in spots or []))


def _spot_text(spot):
    return _join_text(
        spot.get("name"),
        spot.get("description"),
        spot.get("district"),
        spot.get("open_time"),
        spot.get("ticket_reservation"),
        spot.get("address"),
        spot.get("source_note"),
        spot.get("update_note"),
        *(spot.get("emotion_tags") or []),
        *(spot.get("scene_tags") or []),
        *(spot.get("feedback_keywords") or []),
    )


def _contains_term(normalized_text, term):
    normalized_term = _normalize_text(term)
    return bool(normalized_term and normalized_term in normalized_text)


def _clean_list(values):
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        clean_value = _clean_text(value)
        if clean_value and clean_value not in cleaned:
            cleaned.append(clean_value[:40])
    return cleaned


def _enum_value(value, allowed_values):
    clean_value = _clean_text(value)
    return clean_value if clean_value in allowed_values else "unknown"


def _confidence(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(1, number))


def _normalize_text(value):
    return re.sub(r"[\s,，。！？!?；;、/|｜:：·（）()《》“”\"'_-]+", "", str(value or "").lower())


def _join_text(*parts):
    return " ".join(str(part or "") for part in parts if part not in (None, ""))


def _clean_text(value):
    return str(value or "").strip()


def _unique(values):
    unique_values = []
    for value in values:
        _append_unique(unique_values, value)
    return unique_values


def _append_unique(items, value):
    clean_value = _clean_text(value)
    if clean_value and clean_value not in items:
        items.append(clean_value)
