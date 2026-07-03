import copy
import math
import re

from services.intent_matching import score_spot_for_intent
from services.profile_vector import (
    build_route_profile_vector,
    cosine_similarity,
    matched_profile_traits,
)


MIN_SEED_SPOTS_TO_OPTIMIZE = 3
MAX_ROUTE_SPOTS = 4
MIN_RETAINED_SEED_SPOTS = 2
INSERT_MAX_DISTANCE_KM = 1.2
SELECTED_TAG_SCORE = 220
TEXT_TAG_SCORE = 135
SELECTED_MINDSET_FACTOR = 1.15
TEXT_MINDSET_FACTOR = 0.65
TOKEN_SCORE = 4
PROFILE_SPOT_SCORE = 140


def build_dynamic_routes(
    data,
    seed_routes,
    selected_tags,
    selected_mindsets,
    text_tags,
    text_mindsets,
    user_text,
    user_profile,
    possible_score,
    match_percent,
    intent=None,
    limit=3,
):
    candidate_route_ids = {
        route.get("route_id")
        for route in seed_routes or []
        if route.get("route_id")
    }
    scored_spots = _score_spots(
        data.get("spots") or [],
        selected_tags,
        selected_mindsets,
        text_tags,
        text_mindsets,
        user_text,
        user_profile,
        intent or {},
        candidate_route_ids,
    )
    scored_by_id = {item["spot"]["spot_id"]: item for item in scored_spots}
    optimized_routes = []

    for seed_route in seed_routes[: max(1, limit)]:
        optimized_routes.append(
            _optimize_seed_route(
                seed_route,
                scored_spots,
                scored_by_id,
                possible_score,
                match_percent,
                user_profile,
            )
        )

    optimized_routes.sort(key=lambda route: (-route["match_percent"], -route["raw_score"]))
    return optimized_routes[: max(1, limit)]


def _optimize_seed_route(seed_route, scored_spots, scored_by_id, possible_score, match_percent, user_profile):
    route = copy.deepcopy(seed_route)
    route["is_dynamic"] = False
    route["source_route_ids"] = _source_route_ids(route.get("spots", []), route["route_id"])
    route["route_distance_km"] = round(_route_distance_km(route.get("spots", [])), 2)

    seed_spots = route.get("spots", [])
    if len(seed_spots) < MIN_SEED_SPOTS_TO_OPTIMIZE or len(seed_spots) >= MAX_ROUTE_SPOTS:
        return route

    candidate = _best_insert_candidate(seed_spots, scored_spots, scored_by_id)
    if not candidate:
        return route

    insert_index = _best_insert_index(seed_spots, candidate["spot"])
    optimized_spots = copy.deepcopy(seed_spots)
    optimized_spots.insert(insert_index, copy.deepcopy(candidate["spot"]))

    if _retained_seed_spot_count(optimized_spots, route["route_id"]) < MIN_RETAINED_SEED_SPOTS:
        return route

    dynamic_route = copy.deepcopy(route)
    dynamic_route["spots"] = optimized_spots
    dynamic_route["route_spots"] = " → ".join(spot["name"] for spot in optimized_spots)
    dynamic_route["is_dynamic"] = True
    dynamic_route["source_route_ids"] = _source_route_ids(optimized_spots, route["route_id"])
    dynamic_route["route_distance_km"] = round(_route_distance_km(optimized_spots), 2)
    dynamic_route["raw_score"] = round(_dynamic_raw_score(route["raw_score"], candidate), 2)
    dynamic_route["score"] = dynamic_route["raw_score"]
    dynamic_route["match_percent"] = match_percent(dynamic_route["raw_score"], possible_score)
    dynamic_route["matched_tags"] = _merge_unique(route.get("matched_tags", []), candidate["matched_tags"])
    dynamic_route["matched_mindsets"] = _merge_unique(route.get("matched_mindsets", []), candidate["matched_mindsets"])
    dynamic_route["backend_scene_tags"] = _merge_unique(route.get("backend_scene_tags", []), candidate["spot"].get("scene_tags", []))
    dynamic_route["tags"] = _merge_unique(route.get("tags", []), candidate["matched_tags"])
    dynamic_route["mindset_scores"] = _average_mindset_scores(optimized_spots)
    dynamic_route["dominant_mindsets"] = _dominant_mindsets(dynamic_route["mindset_scores"])

    route_vector = build_route_profile_vector(dynamic_route)
    profile_similarity = cosine_similarity(user_profile.get("vector", {}), route_vector)
    dynamic_route["profile_similarity"] = round(profile_similarity, 3)
    if profile_similarity:
        dynamic_route["matched_profile_traits"] = matched_profile_traits(user_profile, route_vector)

    return dynamic_route


def _score_spots(
    spots,
    selected_tags,
    selected_mindsets,
    text_tags,
    text_mindsets,
    user_text,
    user_profile,
    intent=None,
    candidate_route_ids=None,
):
    scored = []
    tokens = _input_tokens(user_text)

    for index, spot in enumerate(spots):
        matched_tags = []
        matched_mindsets = []
        score = 0.0
        spot_text = _spot_search_text(spot)

        for tag in selected_tags:
            if tag in spot.get("emotion_tags", []):
                score += SELECTED_TAG_SCORE
                _append_unique(matched_tags, tag)
            elif tag in spot.get("scene_tags", []):
                score += SELECTED_TAG_SCORE * 0.55
                _append_unique(matched_tags, tag)

        for tag in text_tags:
            if tag in spot.get("emotion_tags", []):
                score += TEXT_TAG_SCORE
                _append_unique(matched_tags, tag)
            elif tag in spot.get("scene_tags", []):
                score += TEXT_TAG_SCORE * 0.55
                _append_unique(matched_tags, tag)

        for mindset in selected_mindsets:
            value = spot.get("mindset_scores", {}).get(mindset, 0)
            if value:
                score += value * SELECTED_MINDSET_FACTOR
                _append_unique(matched_mindsets, mindset)

        for mindset in text_mindsets:
            value = spot.get("mindset_scores", {}).get(mindset, 0)
            if value:
                score += value * TEXT_MINDSET_FACTOR
                _append_unique(matched_mindsets, mindset)

        for token in tokens:
            if token in spot_text:
                score += TOKEN_SCORE

        if user_profile.get("vector"):
            spot_vector = build_route_profile_vector(_spot_as_route(spot))
            profile_similarity = cosine_similarity(user_profile["vector"], spot_vector)
            if profile_similarity:
                score += profile_similarity * PROFILE_SPOT_SCORE

        score += score_spot_for_intent(
            spot=spot,
            selected_tags=list(selected_tags or []) + list(selected_mindsets or []),
            intent=intent or {},
            candidate_route_ids=candidate_route_ids or set(),
        )

        scored.append(
            {
                "index": index,
                "spot": spot,
                "score": score,
                "matched_tags": matched_tags,
                "matched_mindsets": matched_mindsets,
            }
        )

    scored.sort(key=lambda item: (-item["score"], item["index"]))
    return scored


def _best_insert_candidate(seed_spots, scored_spots, scored_by_id):
    seed_ids = {spot["spot_id"] for spot in seed_spots}
    seed_scores = [scored_by_id.get(spot["spot_id"], {}).get("score", 0) for spot in seed_spots]
    minimum_candidate_score = max(seed_scores) * 0.75 if seed_scores else 1
    best = None
    best_value = None

    for item in scored_spots:
        spot = item["spot"]
        if spot["spot_id"] in seed_ids or item["score"] <= 0 or not _has_coordinates(spot):
            continue

        nearest_seed_distance = min(distance_km(spot, seed_spot) for seed_spot in seed_spots)
        if nearest_seed_distance > INSERT_MAX_DISTANCE_KM or item["score"] < minimum_candidate_score:
            continue

        value = item["score"] - nearest_seed_distance * 20
        if best is None or value > best_value:
            best = item
            best_value = value

    return best


def _best_insert_index(seed_spots, candidate_spot):
    best_index = len(seed_spots)
    best_added_distance = None

    for index in range(1, len(seed_spots) + 1):
        previous_spot = seed_spots[index - 1]
        next_spot = seed_spots[index] if index < len(seed_spots) else None
        added_distance = distance_km(previous_spot, candidate_spot)
        if next_spot:
            added_distance += distance_km(candidate_spot, next_spot) - distance_km(previous_spot, next_spot)
        if best_added_distance is None or added_distance < best_added_distance:
            best_index = index
            best_added_distance = added_distance

    return best_index


def _dynamic_raw_score(seed_raw_score, candidate):
    return seed_raw_score


def distance_km(left, right):
    if not _has_coordinates(left) or not _has_coordinates(right):
        return 9999

    lat1 = math.radians(left["lat"])
    lng1 = math.radians(left["lng"])
    lat2 = math.radians(right["lat"])
    lng2 = math.radians(right["lng"])
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _route_distance_km(spots):
    return sum(distance_km(left, right) for left, right in zip(spots, spots[1:]))


def _retained_seed_spot_count(spots, seed_route_id):
    return sum(1 for spot in spots if spot.get("route_id") == seed_route_id)


def _source_route_ids(spots, seed_route_id):
    route_ids = [seed_route_id]
    for spot in spots:
        route_id = spot.get("route_id")
        if route_id and route_id not in route_ids:
            route_ids.append(route_id)
    return route_ids


def _has_coordinates(spot):
    return isinstance(spot.get("lat"), (int, float)) and isinstance(spot.get("lng"), (int, float))


def _spot_as_route(spot):
    return {
        "spots": [spot],
        "mindset_scores": spot.get("mindset_scores", {}),
        "primary_emotion_tags": spot.get("emotion_tags", []),
        "secondary_emotion_tags": [],
    }


def _average_mindset_scores(spots):
    labels = set()
    for spot in spots:
        labels.update(spot.get("mindset_scores", {}).keys())

    scores = {}
    for label in labels:
        values = [spot.get("mindset_scores", {}).get(label, 0) for spot in spots if spot.get("mindset_scores", {}).get(label, 0)]
        scores[label] = round(sum(values) / len(values), 1) if values else 0
    return scores


def _dominant_mindsets(scores):
    return [label for label, _ in sorted(scores.items(), key=lambda item: -item[1])[:3]]


def _spot_search_text(spot):
    parts = [
        spot.get("name", ""),
        spot.get("description", ""),
        spot.get("district", ""),
        spot.get("open_time", ""),
        spot.get("ticket_reservation", ""),
        spot.get("address", ""),
        spot.get("source_note", ""),
        spot.get("update_note", ""),
        *spot.get("emotion_tags", []),
        *spot.get("scene_tags", []),
        *spot.get("feedback_keywords", []),
    ]
    return _normalize_text(" ".join(str(part or "") for part in parts))


def _input_tokens(user_text):
    return [
        _normalize_text(token)
        for token in re.split(r"[\s,，。！？!?；;、/]+", str(user_text or ""))
        if len(_normalize_text(token)) >= 2
    ]


def _normalize_text(value):
    return re.sub(r"[\s,，。！？!?；;、/]+", "", str(value or "").lower())


def _merge_unique(left, right):
    values = list(left or [])
    for value in right or []:
        _append_unique(values, value)
    return values


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)
