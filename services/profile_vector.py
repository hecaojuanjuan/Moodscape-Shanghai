import math


CORE_QUESTION_WEIGHT = 1.0
SKIPPABLE_QUESTION_WEIGHT = 0.35

FEATURE_KEYS = ("quietness", "nature", "culture", "art", "learning", "social", "exploration")

PROFILE_QUESTION_WEIGHTS = {
    "pace": CORE_QUESTION_WEIGHT,
    "healing_space": CORE_QUESTION_WEIGHT,
    "shanghai_style": CORE_QUESTION_WEIGHT,
    "companion": SKIPPABLE_QUESTION_WEIGHT,
    "travel_persona": SKIPPABLE_QUESTION_WEIGHT,
}

PROFILE_OPTIONS = {
    "pace": {
        "slow_stop": {
            "traits": ("慢节奏", "安静"),
            "vector": {
                "feature:quietness": 1.0,
                "mindset:独处": 0.9,
                "mindset:疗愈": 0.8,
                "tag:想慢慢走不赶路": 1.0,
                "tag:想一个人静静": 0.7,
            },
        },
        "clear_content": {
            "traits": ("内容感", "成长"),
            "vector": {
                "feature:learning": 1.0,
                "feature:culture": 0.8,
                "feature:art": 0.6,
                "mindset:成长": 0.9,
                "tag:想看展充电": 1.0,
            },
        },
        "loose_surprise": {
            "traits": ("惊喜", "探索"),
            "vector": {
                "feature:exploration": 1.0,
                "mindset:探索": 0.9,
                "mindset:灵感": 0.8,
                "tag:想探索冷门角落": 1.0,
                "tag:想慢慢走不赶路": 0.4,
            },
        },
        "lively_food": {
            "traits": ("热闹", "烟火气"),
            "vector": {
                "feature:social": 1.0,
                "mindset:社交": 0.9,
                "tag:想边走边吃": 1.0,
                "tag:想夜晚继续玩": 0.5,
            },
        },
    },
    "healing_space": {
        "quiet_street": {
            "traits": ("安静", "疗愈"),
            "vector": {
                "feature:quietness": 1.0,
                "feature:nature": 0.4,
                "mindset:疗愈": 0.9,
                "mindset:独处": 0.5,
                "tag:想一个人静静": 0.8,
                "tag:想逃离人群喘口气": 0.6,
            },
        },
        "art_space": {
            "traits": ("艺术", "灵感"),
            "vector": {
                "feature:art": 1.0,
                "feature:learning": 0.6,
                "mindset:灵感": 0.9,
                "tag:想看展充电": 1.0,
                "tag:想拍照发朋友圈": 0.4,
            },
        },
        "historic_area": {
            "traits": ("历史感", "怀旧"),
            "vector": {
                "feature:culture": 1.0,
                "mindset:怀旧": 1.0,
                "tag:想找回老上海": 1.0,
                "tag:想慢慢走不赶路": 0.3,
            },
        },
        "river_night": {
            "traits": ("夜景", "浪漫"),
            "vector": {
                "mindset:浪漫": 0.9,
                "mindset:疗愈": 0.5,
                "tag:想被夜景治愈": 1.0,
                "tag:想和TA约会": 0.5,
                "tag:想夜晚继续玩": 0.4,
            },
        },
    },
    "shanghai_style": {
        "old_shanghai": {
            "traits": ("老上海", "历史感"),
            "vector": {
                "feature:culture": 1.0,
                "mindset:怀旧": 0.9,
                "tag:想找回老上海": 1.0,
            },
        },
        "future_city": {
            "traits": ("未来感", "城市震撼"),
            "vector": {
                "feature:exploration": 0.6,
                "mindset:探索": 0.6,
                "tag:想体验未来城市": 1.0,
                "tag:想认识上海第一面": 0.5,
            },
        },
        "natural_waterfront": {
            "traits": ("自然", "轻松"),
            "vector": {
                "feature:nature": 1.0,
                "feature:quietness": 0.5,
                "mindset:疗愈": 0.8,
                "tag:想逃离人群喘口气": 1.0,
                "tag:想慢慢走不赶路": 0.5,
            },
        },
        "hidden_corner": {
            "traits": ("小众", "探索"),
            "vector": {
                "feature:exploration": 1.0,
                "mindset:探索": 1.0,
                "mindset:灵感": 0.5,
                "tag:想探索冷门角落": 1.0,
            },
        },
    },
    "companion": {
        "solo": {
            "traits": ("独处",),
            "vector": {
                "feature:quietness": 0.5,
                "mindset:独处": 1.0,
                "tag:想一个人静静": 0.8,
            },
        },
        "couple": {
            "traits": ("约会", "浪漫"),
            "vector": {
                "mindset:浪漫": 1.0,
                "tag:想和TA约会": 1.0,
                "tag:想被夜景治愈": 0.3,
            },
        },
        "family": {
            "traits": ("亲子", "学习"),
            "vector": {
                "feature:learning": 0.8,
                "mindset:成长": 0.6,
                "tag:想带孩子涨见识": 1.0,
            },
        },
        "friends": {
            "traits": ("朋友", "社交"),
            "vector": {
                "feature:social": 0.9,
                "mindset:社交": 1.0,
                "tag:想边走边吃": 0.7,
                "tag:想夜晚继续玩": 0.5,
            },
        },
    },
    "travel_persona": {
        "low_stimulation": {
            "traits": ("低刺激", "慢节奏"),
            "vector": {
                "feature:quietness": 1.0,
                "mindset:疗愈": 0.8,
                "tag:想慢慢走不赶路": 0.7,
                "tag:想逃离人群喘口气": 0.6,
            },
        },
        "inspiration_hunter": {
            "traits": ("灵感",),
            "vector": {
                "feature:art": 0.7,
                "feature:exploration": 0.5,
                "mindset:灵感": 0.8,
                "tag:想看展充电": 0.5,
            },
        },
        "classic_comfort": {
            "traits": ("经典", "舒服"),
            "vector": {
                "mindset:疗愈": 0.5,
                "tag:想认识上海第一面": 0.8,
                "tag:想被夜景治愈": 0.5,
                "tag:想低预算也有仪式感": 0.4,
            },
        },
        "niche_explorer": {
            "traits": ("小众", "探索"),
            "vector": {
                "feature:exploration": 1.0,
                "mindset:探索": 0.9,
                "tag:想探索冷门角落": 1.0,
            },
        },
    },
}


def build_user_profile_vector(profile_answers):
    if not isinstance(profile_answers, dict):
        return _empty_profile()

    vector = {}
    traits = []
    trait_scores = {}
    trait_dimensions = {}
    answered_questions = []
    question_weights = {}

    for question, weight in PROFILE_QUESTION_WEIGHTS.items():
        answer = profile_answers.get(question)
        option = PROFILE_OPTIONS.get(question, {}).get(answer)
        if not option:
            continue

        answered_questions.append(question)
        question_weights[question] = weight

        for dimension, value in option["vector"].items():
            _add_weight(vector, dimension, value * weight)

        for trait in option["traits"]:
            if trait not in traits:
                traits.append(trait)
            _add_weight(trait_scores, trait, weight)
            trait_dimensions.setdefault(trait, set()).update(option["vector"].keys())

    return {
        "vector": _round_values(vector),
        "traits": traits,
        "trait_scores": _round_values(trait_scores),
        "trait_dimensions": {trait: sorted(dimensions) for trait, dimensions in trait_dimensions.items()},
        "answered_questions": answered_questions,
        "question_weights": question_weights,
    }


def build_route_profile_vector(route):
    vector = {}

    spots = route.get("spots", [])
    for key in FEATURE_KEYS:
        values = [
            spot.get("feature_scores", {}).get(key, 0)
            for spot in spots
            if spot.get("feature_scores", {}).get(key, 0)
        ]
        if values:
            vector[f"feature:{key}"] = sum(values) / len(values) / 100

    for label, score in route.get("mindset_scores", {}).items():
        if score:
            vector[f"mindset:{label}"] = score / 100

    for tag in route.get("primary_emotion_tags", []):
        _add_weight(vector, f"tag:{tag}", 1.0)
    for tag in route.get("secondary_emotion_tags", []):
        _add_weight(vector, f"tag:{tag}", 0.65)

    return _round_values(vector)


def cosine_similarity(left, right):
    if not left or not right:
        return 0

    shared_keys = set(left) & set(right)
    if not shared_keys:
        return 0

    dot_product = sum(left[key] * right[key] for key in shared_keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0
    return dot_product / (left_norm * right_norm)


def matched_profile_traits(user_profile, route_vector, limit=4):
    trait_dimensions = user_profile.get("trait_dimensions", {})
    user_vector = user_profile.get("vector", {})
    scored = []

    for trait, dimensions in trait_dimensions.items():
        score = sum(user_vector.get(dimension, 0) * route_vector.get(dimension, 0) for dimension in dimensions)
        if score > 0:
            scored.append((trait, score))

    if not scored:
        return user_profile.get("traits", [])[:limit]

    scored.sort(key=lambda item: -item[1])
    return [trait for trait, _ in scored[:limit]]


def _empty_profile():
    return {
        "vector": {},
        "traits": [],
        "trait_scores": {},
        "trait_dimensions": {},
        "answered_questions": [],
        "question_weights": {},
    }


def _add_weight(target, key, value):
    target[key] = target.get(key, 0) + value


def _round_values(values):
    return {key: round(value, 6) for key, value in values.items() if value}
