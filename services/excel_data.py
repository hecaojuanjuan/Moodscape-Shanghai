from functools import lru_cache
from pathlib import Path

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEL_PATH = PROJECT_ROOT / "上海路线数据.xlsx"


@lru_cache(maxsize=4)
def load_excel_data(excel_path=DEFAULT_EXCEL_PATH):
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        route_rows = _read_table(workbook.worksheets[0])
        spot_rows = _read_table(workbook.worksheets[1])
        tag_rows = _read_table(workbook.worksheets[2])
        mapping_rows = _read_table(workbook.worksheets[3])

        tags = [_normalize_tag(row) for row in tag_rows if row.get("tag_id")]
        spots = _build_spots(spot_rows)
        spots_by_route = _group_spots_by_route(spots)
        mappings_by_tag = _build_mappings(mapping_rows)

        routes = []
        for row in route_rows:
            route_id = row.get("route_id")
            if not route_id:
                continue

            route_spots = spots_by_route.get(route_id, [])
            primary_tags = _split_list(row.get("primary_emotion_tags"))
            secondary_tags = _split_list(row.get("secondary_emotion_tags"))
            route = {
                "route_id": route_id,
                "route_name": _text(row.get("route_name")),
                "route_intro_user_facing": _text(row.get("route_intro_user_facing")),
                "reason": _text(row.get("route_intro_user_facing")),
                "primary_emotion_tags": primary_tags,
                "secondary_emotion_tags": secondary_tags,
                "backend_scene_tags": _split_list(row.get("backend_scene_tags")),
                "tags": primary_tags + [tag for tag in secondary_tags if tag not in primary_tags],
                "suitable_mood": _text(row.get("suitable_mood")),
                "estimated_time": _text(row.get("estimated_time")),
                "budget_level": _text(row.get("budget_level")),
                "route_spots": _text(row.get("route_spots")),
                "ai_script_angle": _text(row.get("ai_script_angle")),
                "spots": route_spots,
            }
            route["mindset_scores"] = _average_mindset_scores(route_spots)
            route["dominant_mindsets"] = _dominant_mindsets(route["mindset_scores"])
            route["tag_match_priority"] = {
                mapping["emotion_tag"]: mapping["priority"]
                for mapping in mappings_by_tag.values()
                if mapping["route_id"] == route_id and isinstance(mapping["priority"], int)
            }
            route["tag_match_reasons"] = {
                mapping["emotion_tag"]: mapping["match_reason"]
                for mapping in mappings_by_tag.values()
                if mapping["route_id"] == route_id and mapping["match_reason"]
            }
            route["suggested_card_copy_by_tag"] = {
                mapping["emotion_tag"]: mapping["suggested_card_copy"]
                for mapping in mappings_by_tag.values()
                if mapping["route_id"] == route_id and mapping["suggested_card_copy"]
            }
            routes.append(route)

        route_ids = {route["route_id"] for route in routes}
        mappings = [
            mapping
            for mapping in mappings_by_tag.values()
            if mapping["route_id"] in route_ids
        ]

        return {
            "routes": routes,
            "spots": spots,
            "tags": tags,
            "mappings": mappings,
            "mindset_tags": _extract_mindset_tags(spot_rows),
        }
    finally:
        workbook.close()


def _read_table(sheet):
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=4, max_row=4))]
    rows = []
    for values in sheet.iter_rows(min_row=5, values_only=True):
        row = {
            str(header): value
            for header, value in zip(headers, values)
            if header is not None
        }
        if any(value not in (None, "") for value in row.values()):
            rows.append(row)
    return rows


def _normalize_tag(row):
    return {
        "tag_id": _text(row.get("tag_id")),
        "emotion_tag": _text(row.get("emotion_tag")),
        "user_button_text": _text(row.get("user_button_text")),
        "user_state": _text(row.get("user_state")),
        "experience_need": _text(row.get("experience_need")),
        "recommended_routes": _split_list(row.get("recommended_routes")),
        "example_spots": _split_list(row.get("example_spots")),
        "website_display_copy": _text(row.get("website_display_copy")),
        "ai_script_tone": _text(row.get("ai_script_tone")),
        "backend_scene_tags": _split_list(row.get("backend_scene_tags")),
    }


def _build_spots(spot_rows):
    spots = []
    for row in spot_rows:
        route_id = _text(row.get("route_id"))
        spot_id = row.get("spot_id")
        if not spot_id:
            continue

        lat, lng = _parse_lat_lng(row.get("经纬度（WGS84）"))
        spot = {
            "spot_id": _text(spot_id),
            "route_id": route_id,
            "spot_order": _int(row.get("spot_order")),
            "name": _text(row.get("spot_name")),
            "description": _text(row.get("user_experience_value")),
            "district": _text(row.get("district")),
            "lat": lat,
            "lng": lng,
            "emotion_tags": _split_list(row.get("emotion_tags")),
            "scene_tags": _split_list(row.get("scene_tags")),
            "open_time": _text(row.get("open_time")),
            "ticket_reservation": _text(row.get("ticket_reservation")),
            "feedback_keywords": _split_list(row.get("feedback_keywords")),
            "source_note": _text(row.get("source_note")),
            "source_url": _text(row.get("source_url")),
            "update_note": _text(row.get("update_note")),
            "address": _text(row.get("地址")),
            "feature_scores": {
                "quietness": _number(row.get("安静度 Quietness")),
                "nature": _number(row.get("自然度 Nature")),
                "culture": _number(row.get("文化度 Culture")),
                "art": _number(row.get("艺术度 Art")),
                "learning": _number(row.get("学习度 Learning")),
                "social": _number(row.get("社交度 Social")),
                "exploration": _number(row.get("探索度 Exploration")),
            },
            "mindset_scores": _parse_mindset_scores(row.get("心境指数（图1百分比计算）")),
        }
        spots.append(spot)

    return spots


def _group_spots_by_route(spots):
    spots_by_route = {}
    for spot in spots:
        if not spot["route_id"]:
            continue
        spots_by_route.setdefault(spot["route_id"], []).append(spot)
    for spots in spots_by_route.values():
        spots.sort(key=lambda spot: spot["spot_order"])
    return spots_by_route


def _build_mappings(mapping_rows):
    mappings = {}
    for row in mapping_rows:
        emotion_tag = _text(row.get("emotion_tag"))
        route_id = _text(row.get("route_id"))
        if not emotion_tag or not route_id:
            continue
        mappings[(emotion_tag, route_id)] = {
            "tag_id": _text(row.get("tag_id")),
            "emotion_tag": emotion_tag,
            "route_id": route_id,
            "route_name": _text(row.get("route_name")),
            "priority": _int(row.get("priority")),
            "match_reason": _text(row.get("match_reason")),
            "suggested_card_copy": _text(row.get("suggested_card_copy")),
        }
    return mappings


def _extract_mindset_tags(spot_rows):
    for row in spot_rows:
        scores = _parse_mindset_scores(row.get("心境指数（图1百分比计算）"))
        if scores:
            return list(scores.keys())
    return []


def _parse_mindset_scores(raw_value):
    scores = {}
    for item in _split_list(raw_value):
        if ":" not in item:
            continue
        label, raw_score = item.split(":", 1)
        scores[label.strip()] = _int(raw_score)
    return scores


def _average_mindset_scores(spots):
    scores = {}
    labels = spots[0]["mindset_scores"].keys() if spots else []
    for label in labels:
        values = [
            spot["mindset_scores"][label]
            for spot in spots
            if label in spot["mindset_scores"]
        ]
        scores[label] = round(sum(values) / len(values), 1) if values else 0
    return scores


def _dominant_mindsets(scores):
    return [
        label
        for label, _ in sorted(scores.items(), key=lambda item: -item[1])[:3]
    ]


def _parse_lat_lng(raw_value):
    parts = [part.strip() for part in str(raw_value or "").split(",")]
    if len(parts) != 2:
        return None, None
    return float(parts[0]), float(parts[1])


def _split_list(value):
    return [part.strip() for part in str(value or "").split("；") if part and part.strip()]


def _text(value):
    return "" if value is None else str(value).strip()


def _int(value):
    if value in (None, ""):
        return 0
    return int(float(value))


def _number(value):
    if value in (None, ""):
        return 0
    number = float(value)
    return int(number) if number.is_integer() else number
