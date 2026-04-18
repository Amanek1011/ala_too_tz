from collections import defaultdict

from .data import get_region

try:
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:  # pragma: no cover - optional dependency
    DictVectorizer = None
    cosine_similarity = None


INTEREST_KEYS = ("history", "nature", "culture", "adventure", "wellness", "city")

INTEREST_LABELS = {
    "ru": {
        "history": "история",
        "nature": "природа",
        "culture": "культура",
        "adventure": "активный отдых",
        "wellness": "оздоровление",
        "city": "городская среда",
    },
    "en": {
        "history": "history",
        "nature": "nature",
        "culture": "culture",
        "adventure": "active travel",
        "wellness": "wellness",
        "city": "city life",
    },
    "ky": {
        "history": "тарых",
        "nature": "жаратылыш",
        "culture": "маданият",
        "adventure": "жигердүү эс алуу",
        "wellness": "ден соолук",
        "city": "шаардык чөйрө",
    },
}

ACTIVITY_LABELS = {
    "ru": {"low": "спокойный", "medium": "сбалансированный", "high": "активный"},
    "en": {"low": "relaxed", "medium": "balanced", "high": "active"},
    "ky": {"low": "жай", "medium": "тең салмактуу", "high": "активдүү"},
}

ACCESSIBILITY_LABELS = {
    "ru": {
        "full": "полностью доступно",
        "partial": "частично доступно",
        "limited": "требует хорошей физической подготовки",
    },
    "en": {
        "full": "fully accessible",
        "partial": "partially accessible",
        "limited": "needs strong physical mobility",
    },
    "ky": {
        "full": "толугу менен жеткиликтүү",
        "partial": "жарым-жартылай жеткиликтүү",
        "limited": "жакшы физикалык даярдык керек",
    },
}


def _label(lang, bucket, key):
    return bucket.get(lang, bucket["en"]).get(key, key)


def interest_label(lang, key):
    return _label(lang, INTEREST_LABELS, key)


def activity_label(lang, key):
    return _label(lang, ACTIVITY_LABELS, key)


def accessibility_label(lang, key):
    return _label(lang, ACCESSIBILITY_LABELS, key)


def _localize_region_name(region_id, lang):
    region = get_region(region_id) or {}
    if lang == "ky" and region.get("name_ky"):
        return region["name_ky"]
    if lang == "en" and region.get("name_en"):
        return region["name_en"]
    return region.get("name_ru") or region.get("name") or region_id


def _build_landmark_features(landmark):
    tags = set(landmark.theme_tags or [])
    features = {
        "physical_intensity": landmark.physical_intensity / 5,
        "recommended_visit_hours": landmark.recommended_visit_hours / 12,
        "family_friendly": 1 if landmark.family_friendly else 0,
        "senior_friendly": 1 if landmark.senior_friendly else 0,
        f"category_{landmark.category}": 1,
        f"accessibility_{landmark.accessibility_level}": 1,
    }
    for key in INTEREST_KEYS:
        features[f"tag_{key}"] = 1 if key in tags else 0
    return features


def _build_profile_features(cleaned_data):
    activity_targets = {"low": 0.25, "medium": 0.6, "high": 0.9}
    features = {
        "physical_intensity": activity_targets[cleaned_data["physical_activity"]],
        "recommended_visit_hours": min(cleaned_data["duration_hours"] / 12, 1),
        "family_friendly": 1 if cleaned_data["with_children"] else 0,
        "senior_friendly": 1 if cleaned_data["age"] >= 60 else 0,
        "accessibility_full": 1 if cleaned_data["accessibility_required"] else 0,
        "accessibility_partial": 0.8 if cleaned_data["accessibility_required"] else 0,
        "accessibility_limited": 0 if cleaned_data["accessibility_required"] else 0.2,
    }
    for key in INTEREST_KEYS:
        features[f"tag_{key}"] = 1 if key in cleaned_data["interests"] else 0
        features[f"category_{key}"] = 1 if key in cleaned_data["interests"] else 0
    return features


def _cosine_scores(landmarks, cleaned_data):
    if DictVectorizer is None or cosine_similarity is None:
        return {}
    vectorizer = DictVectorizer(sparse=False)
    landmark_vectors = vectorizer.fit_transform([_build_landmark_features(item) for item in landmarks])
    profile_vector = vectorizer.transform([_build_profile_features(cleaned_data)])
    scores = cosine_similarity(landmark_vectors, profile_vector).ravel()
    return {landmark.id: float(score) for landmark, score in zip(landmarks, scores)}


def _manual_score(landmark, cleaned_data):
    tags = set(landmark.theme_tags or [])
    activity_target = {"low": 1.5, "medium": 3, "high": 4.5}[cleaned_data["physical_activity"]]
    score = 0.25

    matched_interests = tags.intersection(cleaned_data["interests"])
    score += 0.22 * len(matched_interests)

    if landmark.category in cleaned_data["interests"]:
        score += 0.18

    if cleaned_data["accessibility_required"]:
        if landmark.accessibility_level == "full":
            score += 0.22
        elif landmark.accessibility_level == "partial":
            score += 0.12
        else:
            score -= 0.4

    if cleaned_data["with_children"] and landmark.family_friendly:
        score += 0.18

    if cleaned_data["age"] >= 60 and landmark.senior_friendly:
        score += 0.18

    score += max(0, 0.22 - abs(landmark.physical_intensity - activity_target) * 0.06)
    score += max(0, 0.14 - abs(landmark.recommended_visit_hours - max(1, cleaned_data["duration_hours"] / 3)) * 0.03)
    return score


def _compose_reasons(landmark, cleaned_data, lang):
    reasons = []
    matched_interests = [interest_label(lang, item) for item in cleaned_data["interests"] if item in (landmark.theme_tags or [])]
    if matched_interests:
        if lang == "ru":
            reasons.append(f"Совпадает с интересами: {', '.join(matched_interests)}.")
        elif lang == "ky":
            reasons.append(f"Кызыгууларыңызга шайкеш: {', '.join(matched_interests)}.")
        else:
            reasons.append(f"Matches your interests: {', '.join(matched_interests)}.")

    if cleaned_data["accessibility_required"] and landmark.accessibility_level in {"full", "partial"}:
        if lang == "ru":
            reasons.append(f"Подходит для доступного маршрута: {accessibility_label(lang, landmark.accessibility_level)}.")
        elif lang == "ky":
            reasons.append(f"Жеткиликтүү маршрутка туура келет: {accessibility_label(lang, landmark.accessibility_level)}.")
        else:
            reasons.append(f"Works for an accessible route: {accessibility_label(lang, landmark.accessibility_level)}.")

    if cleaned_data["with_children"] and landmark.family_friendly:
        if lang == "ru":
            reasons.append("Подходит для семейной поездки и не требует перегрузки.")
        elif lang == "ky":
            reasons.append("Үй-бүлөлүк сапарга ылайыктуу жана ашыкча күч талап кылбайт.")
        else:
            reasons.append("Suitable for family travel without excessive strain.")

    if cleaned_data["age"] >= 60 and landmark.senior_friendly:
        if lang == "ru":
            reasons.append("Комфортен для более спокойного темпа и старшего возраста.")
        elif lang == "ky":
            reasons.append("Улуураак курак жана жай темп үчүн ыңгайлуу.")
        else:
            reasons.append("Comfortable for a calmer pace and senior travelers.")

    if not reasons:
        if lang == "ru":
            reasons.append("Подходит по балансу времени, темпа и тематической ценности.")
        elif lang == "ky":
            reasons.append("Убакыт, темп жана мазмун боюнча тең салмактуу тандоо.")
        else:
            reasons.append("A balanced pick for time, pace, and thematic value.")

    return reasons[:3]


def _route_difficulty(selected_items):
    if not selected_items:
        return "easy"
    average_intensity = sum(item["landmark"].physical_intensity for item in selected_items) / len(selected_items)
    if average_intensity <= 2:
        return "easy"
    if average_intensity <= 3.5:
        return "medium"
    return "hard"


def _difficulty_label(lang, key):
    labels = {
        "ru": {"easy": "лёгкий", "medium": "средний", "hard": "активный"},
        "en": {"easy": "easy", "medium": "moderate", "hard": "active"},
        "ky": {"easy": "жеңил", "medium": "орточо", "hard": "активдүү"},
    }
    return _label(lang, labels, key)


def _route_title(lang, primary_interest, region_names):
    interest = interest_label(lang, primary_interest)
    if len(region_names) == 1:
        if lang == "ru":
            return f"{interest.title()} маршрут по региону {region_names[0]}"
        if lang == "ky":
            return f"{region_names[0]} боюнча {interest} маршруту"
        return f"{interest.title()} route through {region_names[0]}"
    if lang == "ru":
        return f"Комбинированный маршрут: {interest} и культурные акценты"
    if lang == "ky":
        return f"Аралаш маршрут: {interest} жана маданий басым"
    return f"Blended route: {interest} and cultural highlights"


def _route_summary(lang, cleaned_data, region_names, selected_items):
    hours = sum(item["landmark"].recommended_visit_hours for item in selected_items)
    region_text = ", ".join(region_names[:2])
    if lang == "ru":
        return (
            f"Маршрут рассчитан на {cleaned_data['duration_hours']} ч., включает {len(selected_items)} остановки "
            f"и делает акцент на {region_text}. Оценочное время на посещение объектов: {hours} ч."
        )
    if lang == "ky":
        return (
            f"Маршрут {cleaned_data['duration_hours']} саатка ылайыкталган, {len(selected_items)} токтоону камтыйт "
            f"жана {region_text} багытына басым жасайт. Болжолдуу көрүү убактысы: {hours} саат."
        )
    return (
        f"This route fits into {cleaned_data['duration_hours']} hours, includes {len(selected_items)} stops, "
        f"and focuses on {region_text}. Estimated visit time: {hours} hours."
    )


def _profile_summary(lang, cleaned_data):
    interests = ", ".join(interest_label(lang, item) for item in cleaned_data["interests"])
    activity = activity_label(lang, cleaned_data["physical_activity"])
    if lang == "ru":
        parts = [f"Возраст: {cleaned_data['age']}", f"интересы: {interests}", f"темп: {activity}"]
        if cleaned_data["with_children"]:
            parts.append("семейный формат")
        if cleaned_data["accessibility_required"]:
            parts.append("маршрут с доступной средой")
        return "; ".join(parts)
    if lang == "ky":
        parts = [f"Жашы: {cleaned_data['age']}", f"кызыгуулары: {interests}", f"темп: {activity}"]
        if cleaned_data["with_children"]:
            parts.append("үй-бүлөлүк формат")
        if cleaned_data["accessibility_required"]:
            parts.append("жеткиликтүү маршрут")
        return "; ".join(parts)
    parts = [f"Age: {cleaned_data['age']}", f"interests: {interests}", f"pace: {activity}"]
    if cleaned_data["with_children"]:
        parts.append("family-friendly mode")
    if cleaned_data["accessibility_required"]:
        parts.append("accessible route")
    return "; ".join(parts)


def recommend_route(landmarks, cleaned_data, lang="ru"):
    if not landmarks:
        return None

    vector_scores = _cosine_scores(landmarks, cleaned_data)
    scored_items = []
    for landmark in landmarks:
        score = _manual_score(landmark, cleaned_data)
        if vector_scores:
            score = score * 0.6 + vector_scores.get(landmark.id, 0) * 0.4
        if cleaned_data["accessibility_required"] and landmark.accessibility_level == "limited":
            score -= 0.25
        scored_items.append(
            {
                "landmark": landmark,
                "score": score,
                "reasons": _compose_reasons(landmark, cleaned_data, lang),
            }
        )

    scored_items.sort(key=lambda item: item["score"], reverse=True)

    region_scores = defaultdict(float)
    region_buckets = defaultdict(list)
    for item in scored_items:
        region_scores[item["landmark"].region] += item["score"]
        region_buckets[item["landmark"].region].append(item)

    preferred_region_count = 1 if cleaned_data["duration_hours"] <= 7 else 2
    chosen_regions = [
        region_id
        for region_id, _ in sorted(region_scores.items(), key=lambda pair: pair[1], reverse=True)[:preferred_region_count]
    ]

    max_stops = max(2, min(6, cleaned_data["duration_hours"] // 2 + 1))
    remaining_hours = max(1, cleaned_data["duration_hours"])
    selected_items = []
    used_landmarks = set()

    for region_id in chosen_regions:
        for item in region_buckets[region_id]:
            landmark = item["landmark"]
            if landmark.id in used_landmarks:
                continue
            if selected_items and len(selected_items) >= max_stops:
                break
            if selected_items and landmark.recommended_visit_hours > remaining_hours + 1:
                continue
            selected_items.append(item)
            used_landmarks.add(landmark.id)
            remaining_hours -= landmark.recommended_visit_hours
            if len(selected_items) >= max_stops:
                break

    for item in scored_items:
        if len(selected_items) >= max_stops:
            break
        landmark = item["landmark"]
        if landmark.id in used_landmarks:
            continue
        if landmark.recommended_visit_hours > remaining_hours + 1 and selected_items:
            continue
        selected_items.append(item)
        used_landmarks.add(landmark.id)
        remaining_hours -= landmark.recommended_visit_hours

    if not selected_items and scored_items:
        selected_items.append(scored_items[0])

    if not selected_items:
        return None

    selected_region_names = []
    for region_id in chosen_regions:
        if any(item["landmark"].region == region_id for item in selected_items):
            selected_region_names.append(_localize_region_name(region_id, lang))
    if not selected_region_names:
        selected_region_names.append(_localize_region_name(selected_items[0]["landmark"].region, lang))

    dominant_interest = cleaned_data["interests"][0] if cleaned_data["interests"] else selected_items[0]["landmark"].category
    difficulty_key = _route_difficulty(selected_items)

    return {
        "title": _route_title(lang, dominant_interest, selected_region_names),
        "summary": _route_summary(lang, cleaned_data, selected_region_names, selected_items),
        "profile_summary": _profile_summary(lang, cleaned_data),
        "difficulty_key": difficulty_key,
        "difficulty_label": _difficulty_label(lang, difficulty_key),
        "selected_regions": selected_region_names,
        "total_hours": sum(item["landmark"].recommended_visit_hours for item in selected_items),
        "stops": selected_items,
        "alternatives": [item for item in scored_items if item["landmark"].id not in used_landmarks][:3],
    }
