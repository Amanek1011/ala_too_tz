import json
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.db.models import Avg, Count, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import activate

from .data import get_all_regions, get_highlights, get_region
from .forms import ReviewForm, RouteRequestForm, SignInForm, SignUpForm
from .models import ARMarker, Landmark, Review
from .recommendations import accessibility_label, activity_label, recommend_route
from .translations import (
    LANGUAGE_LABELS,
    get_supported_language,
    get_ui_texts,
    review_word,
    text,
)

IMAGES_DIR = Path(settings.BASE_DIR) / "apps" / "attractions" / "static" / "attractions" / "images"

REGION_COORDINATE_HINTS = {
    "chuy": (42.87, 74.59),
    "bishkek": (42.8746, 74.6122),
    "talas": (42.52, 72.24),
    "jalal-abad": (40.93, 73.0),
    "osh-city": (40.53, 72.8),
    "osh": (39.83, 72.85),
    "batken": (40.06, 70.82),
    "naryn": (41.43, 75.99),
    "issyk-kul": (42.49, 77.35),
}

REGION_COORDINATE_OFFSETS = [
    (0.0, 0.0),
    (0.08, 0.14),
    (-0.12, 0.1),
    (0.15, -0.08),
    (-0.08, -0.12),
    (0.18, 0.05),
]

CATEGORY_LABELS = {
    "ru": {
        "history": "История",
        "nature": "Природа",
        "culture": "Культура",
        "adventure": "Приключения",
        "wellness": "Оздоровление",
        "city": "Город",
    },
    "en": {
        "history": "History",
        "nature": "Nature",
        "culture": "Culture",
        "adventure": "Adventure",
        "wellness": "Wellness",
        "city": "City",
    },
    "ky": {
        "history": "Тарых",
        "nature": "Жаратылыш",
        "culture": "Маданият",
        "adventure": "Укмуш окуя",
        "wellness": "Ден соолук",
        "city": "Шаар",
    },
}

AR_MARKER_TYPE_LABELS = {
    "ru": {
        "reconstruction": "Реконструкция",
        "costume": "Костюм",
        "story": "История",
        "panorama": "Панорама",
    },
    "en": {
        "reconstruction": "Reconstruction",
        "costume": "Costume",
        "story": "Story",
        "panorama": "Panorama",
    },
    "ky": {
        "reconstruction": "Калыбына келтирүү",
        "costume": "Кийим",
        "story": "Окуя",
        "panorama": "Панорама",
    },
}


def get_language(request):
    requested_language = request.GET.get("lang") or request.POST.get("lang") or "ru"
    return get_supported_language(requested_language)


def prepare_language(request):
    lang = get_language(request)
    activate(lang)
    request.LANGUAGE_CODE = lang
    return lang


def with_lang(url, lang):
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}lang={lang}"


def build_language_links(request):
    links = []
    for code, label in LANGUAGE_LABELS.items():
        params = request.GET.copy()
        params["lang"] = code
        query_string = params.urlencode()
        url = f"{request.path}?{query_string}" if query_string else request.path
        links.append(
            {
                "code": code,
                "label": label,
                "url": url,
                "active": code == get_language(request),
            }
        )
    return links


def build_context(request, lang, **kwargs):
    context = {
        "lang": lang,
        "ui": get_ui_texts(lang),
        "language_links": build_language_links(request),
        "user_greeting": text(lang, "greeting", username=request.user.username) if request.user.is_authenticated else "",
    }
    context.update(kwargs)
    return context


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return ""


def build_auth_link(route_name, lang, next_url=""):
    params = {"lang": lang}
    if next_url:
        params["next"] = next_url
    return f"{reverse(route_name)}?{urlencode(params)}"


def localize_data_value(data, field_name, lang):
    language_variants = {
        "ru": [f"{field_name}_ru", field_name, f"{field_name}_en", f"{field_name}_ky"],
        "en": [f"{field_name}_en", field_name, f"{field_name}_ru", f"{field_name}_ky"],
        "ky": [f"{field_name}_ky", f"{field_name}_ru", field_name, f"{field_name}_en"],
    }
    for key in language_variants[lang]:
        value = data.get(key)
        if value:
            return value
    return ""


def localize_model_value(instance, field_name, lang):
    language_variants = {
        "ru": [field_name, f"{field_name}_en", f"{field_name}_ky"],
        "en": [f"{field_name}_en", field_name, f"{field_name}_ky"],
        "ky": [f"{field_name}_ky", field_name, f"{field_name}_en"],
    }
    for attr in language_variants[lang]:
        value = getattr(instance, attr, "")
        if value:
            return value
    return ""


def localize_landmark_value(landmark, field_name, lang):
    return localize_model_value(landmark, field_name, lang)


def image_exists(image_name):
    return bool(image_name and (IMAGES_DIR / image_name).exists())


def image_url(image_name):
    if not image_exists(image_name):
        return ""
    return static(f"attractions/images/{image_name}")


def label_from_map(labels_map, lang, key):
    return labels_map.get(lang, labels_map["en"]).get(key, key)


def category_label(lang, key):
    return label_from_map(CATEGORY_LABELS, lang, key)


def ar_marker_type_label(lang, key):
    return label_from_map(AR_MARKER_TYPE_LABELS, lang, key)


def intensity_bucket(intensity):
    if intensity <= 2:
        return "low"
    if intensity <= 3:
        return "medium"
    return "high"


def fallback_coordinates(region_id, index):
    base = REGION_COORDINATE_HINTS.get(region_id)
    if not base:
        return None, None
    offset_lat, offset_lng = REGION_COORDINATE_OFFSETS[index % len(REGION_COORDINATE_OFFSETS)]
    return round(base[0] + offset_lat, 4), round(base[1] + offset_lng, 4)


def infer_landmark_profile(landmark_data):
    text_blob = " ".join(
        str(landmark_data.get(key, "")).lower()
        for key in ("name", "name_en", "name_ru", "name_ky", "description", "description_en", "description_ru", "description_ky")
    )

    keyword_groups = {
        "nature": ["lake", "waterfall", "forest", "valley", "gorge", "park", "springs", "canyon", "biosphere"],
        "history": ["tower", "ancient", "museum", "fortress", "archaeological", "ruins", "caravanserai", "memorial", "sacred"],
        "culture": ["bazaar", "festival", "ordo", "square", "boulevard", "sanatorium", "museum", "tradition"],
        "adventure": ["peak", "ridge", "base camp", "trail", "viewpoint", "gorge", "waterfall", "mountain"],
        "wellness": ["springs", "sanatorium", "healing", "resort"],
        "city": ["city", "square", "bazaar", "boulevard", "museum"],
    }
    tags = {key for key, words in keyword_groups.items() if any(word in text_blob for word in words)}
    if not tags:
        tags = {"culture"}

    category_priority = ("history", "nature", "culture", "adventure", "wellness", "city")
    category = next((item for item in category_priority if item in tags), "culture")

    physical_intensity = 2
    if any(word in text_blob for word in ["peak", "base camp", "ridge"]):
        physical_intensity = 5
    elif any(word in text_blob for word in ["waterfall", "gorge", "forest", "trail", "mountain", "valley"]):
        physical_intensity = 4
    elif any(word in text_blob for word in ["lake", "park", "canyon", "springs"]):
        physical_intensity = 3
    elif any(word in text_blob for word in ["museum", "square", "bazaar", "city", "boulevard"]):
        physical_intensity = 1

    if any(word in text_blob for word in ["base camp", "peak", "gorge", "waterfall"]):
        accessibility_level = "limited"
    elif any(word in text_blob for word in ["park", "lake", "sanatorium", "tower", "forest", "springs", "viewpoint"]):
        accessibility_level = "partial"
    else:
        accessibility_level = "full"

    family_friendly = (
        physical_intensity <= 3
        and accessibility_level != "limited"
        and any(word in text_blob for word in ["park", "lake", "museum", "square", "bazaar", "tower", "city", "boulevard"])
    )
    senior_friendly = physical_intensity <= 2 and accessibility_level in {"full", "partial"}

    recommended_visit_hours = 2
    if category in {"adventure", "nature"} and physical_intensity >= 4:
        recommended_visit_hours = 3
    elif category in {"history", "city"} and physical_intensity <= 2:
        recommended_visit_hours = 1

    return {
        "category": category,
        "theme_tags": sorted(tags),
        "accessibility_level": accessibility_level,
        "physical_intensity": physical_intensity,
        "family_friendly": family_friendly,
        "senior_friendly": senior_friendly,
        "recommended_visit_hours": recommended_visit_hours,
    }


def translated_ar_content(landmark, kind, lang):
    name = localize_landmark_value(landmark, "name", lang)
    content = {
        "reconstruction": {
            "ru": (
                "Историческая реконструкция",
                f"Наведите камеру, чтобы увидеть, как {name} мог выглядеть во времена Шёлкового пути.",
            ),
            "en": (
                "Historical reconstruction",
                f"Point the camera to imagine how {name} may have looked during the Silk Road era.",
            ),
            "ky": (
                "Тарыхый калыбына келтирүү",
                f"Камераны багыттап, {name} Жибек жолу доорунда кандай көрүнүштө болгонун элестетиңиз.",
            ),
        },
        "costume": {
            "ru": (
                "Традиционный костюм",
                f"AR-слой показывает силуэт в национальном костюме, связанном с культурой места {name}.",
            ),
            "en": (
                "Traditional costume",
                f"The AR layer adds a traditional costume silhouette connected to the culture of {name}.",
            ),
            "ky": (
                "Салттуу кийим",
                f"AR катмары {name} менен байланышкан улуттук кийимдин образын көрсөтөт.",
            ),
        },
        "story": {
            "ru": (
                "История и легенда",
                f"Откройте короткий сюжет о прошлом, людях и символах, связанных с {name}.",
            ),
            "en": (
                "Story and legend",
                f"Open a short story about the people, symbols, and history connected to {name}.",
            ),
            "ky": (
                "Окуя жана уламыш",
                f"{name} менен байланышкан тарых, каармандар жана белгилер тууралуу кыска окуяны көрүңүз.",
            ),
        },
        "panorama": {
            "ru": (
                "Панорамный слой",
                f"Наложите в камере обзорные подсказки, сезонные линии и точки интереса для {name}.",
            ),
            "en": (
                "Panoramic overlay",
                f"Use live-view hints, seasonal lines, and nearby highlights to explore {name}.",
            ),
            "ky": (
                "Панорамалык катмар",
                f"{name} үчүн камерада панорамалык багыттарды жана кызыктуу чекиттерди ачыңыз.",
            ),
        },
    }
    return content[kind][lang]


def build_default_ar_marker_payloads(landmark):
    primary_by_category = {
        "history": "reconstruction",
        "culture": "costume",
        "nature": "panorama",
        "adventure": "panorama",
        "wellness": "panorama",
        "city": "story",
    }
    primary_kind = primary_by_category.get(landmark.category, "story")
    secondary_kind = "story" if primary_kind != "story" else "costume"
    kinds = [primary_kind, secondary_kind]

    payloads = []
    for index, kind in enumerate(kinds):
        ru_title, ru_description = translated_ar_content(landmark, kind, "ru")
        en_title, en_description = translated_ar_content(landmark, kind, "en")
        ky_title, ky_description = translated_ar_content(landmark, kind, "ky")
        payloads.append(
            {
                "title": ru_title,
                "title_en": en_title,
                "title_ky": ky_title,
                "description": ru_description,
                "description_en": en_description,
                "description_ky": ky_description,
                "marker_type": kind,
                "icon": kind,
                "distance_meters": 12 + (index * 10),
                "sort_order": index,
                "is_active": True,
            }
        )
    return payloads


def ensure_landmark_ar_markers(landmark):
    if landmark.ar_markers.exists():
        return
    for payload in build_default_ar_marker_payloads(landmark):
        ARMarker.objects.create(landmark=landmark, **payload)


def sync_region_landmarks(region_id):
    region = get_region(region_id)
    if region is None:
        raise Http404("Регион не найден")

    for index, landmark_data in enumerate(region.get("landmarks", [])):
        english_name = landmark_data.get("name_en") or landmark_data.get("name") or landmark_data.get("name_ru")
        russian_name = landmark_data.get("name_ru") or english_name
        kyrgyz_name = landmark_data.get("name_ky") or russian_name

        landmark = (
            Landmark.objects.filter(region=region_id, name_en=english_name).first()
            or Landmark.objects.filter(region=region_id, name=russian_name).first()
            or Landmark.objects.filter(region=region_id, name=english_name).first()
        )

        lat = landmark_data.get("lat")
        lng = landmark_data.get("lng")
        if lat is None or lng is None:
            lat, lng = fallback_coordinates(region_id, index)

        inferred_profile = infer_landmark_profile(landmark_data)
        payload = {
            "name": russian_name,
            "name_en": english_name,
            "name_ky": kyrgyz_name,
            "region": region_id,
            "image": landmark_data.get("image", ""),
            "description": landmark_data.get("description_ru") or landmark_data.get("description") or "",
            "description_en": landmark_data.get("description_en") or landmark_data.get("description") or "",
            "description_ky": landmark_data.get("description_ky") or landmark_data.get("description_ru") or "",
            "latitude": lat,
            "longitude": lng,
            **inferred_profile,
        }

        if landmark is None:
            landmark = Landmark.objects.create(**payload)
            ensure_landmark_ar_markers(landmark)
            continue

        changed = False
        for field_name, value in payload.items():
            if getattr(landmark, field_name) != value:
                setattr(landmark, field_name, value)
                changed = True
        if changed:
            landmark.save()
        ensure_landmark_ar_markers(landmark)


def sync_all_regions():
    for region in get_all_regions():
        sync_region_landmarks(region["id"])


def get_landmark_source(landmark):
    region = get_region(landmark.region)
    if region is None:
        return {}

    for item in region.get("landmarks", []):
        candidates = {
            item.get("name_en"),
            item.get("name"),
            item.get("name_ru"),
            item.get("name_ky"),
        }
        if landmark.name_en in candidates or landmark.name in candidates or landmark.name_ky in candidates:
            return item
    return {}


def serialize_region(region, lang):
    return {
        "id": region["id"],
        "name": localize_data_value(region, "name", lang),
        "tagline": localize_data_value(region, "tagline", lang),
        "description": localize_data_value(region, "description", lang),
        "color": region["color"],
        "path": region["path"],
        "cx": region["cx"],
        "cy": region["cy"],
        "r": region["r"],
        "g": region["g"],
        "b": region["b"],
    }


def build_landmark_description(landmark, source, region_name, lang):
    source_description = localize_data_value(source, "description", lang) if source else ""
    db_description = localize_landmark_value(landmark, "description", lang)
    return source_description or db_description or text(
        lang,
        "landmark_fallback_description",
        name=localize_landmark_value(landmark, "name", lang),
        region=region_name,
    )


def serialize_review(review):
    return {
        "user": review.user.username,
        "rating": review.rating,
        "comment": review.comment,
        "created_at": review.created_at,
    }


def build_landmark_card(landmark, source, lang, region_name):
    reviews = [serialize_review(review) for review in landmark.review_set.all()[:3]]
    average_rating = landmark.average_rating or 0
    review_count = landmark.review_count or 0

    return {
        "id": landmark.id,
        "name": localize_data_value(source, "name", lang) or localize_landmark_value(landmark, "name", lang),
        "description": build_landmark_description(landmark, source, region_name, lang),
        "image": landmark.image,
        "image_url": image_url(landmark.image),
        "has_image": image_exists(landmark.image),
        "average_rating": average_rating,
        "rounded_average": int(round(average_rating)) if average_rating else 0,
        "review_count": review_count,
        "review_word": review_word(lang, review_count),
        "reviews": reviews,
    }


def get_city_markers(lang):
    city_labels = {
        "ru": {
            "bishkek": "Бишкек",
            "osh-city": "Ош",
            "karakol": "Каракол",
            "naryn-city": "Нарын",
        },
        "en": {
            "bishkek": "Bishkek",
            "osh-city": "Osh",
            "karakol": "Karakol",
            "naryn-city": "Naryn",
        },
        "ky": {
            "bishkek": "Бишкек",
            "osh-city": "Ош",
            "karakol": "Каракол",
            "naryn-city": "Нарын",
        },
    }

    return [
        {"id": "bishkek", "label": city_labels[lang]["bishkek"], "cx": 480, "cy": 175},
        {"id": "osh-city", "label": city_labels[lang]["osh-city"], "cx": 292, "cy": 400},
        {"id": "karakol", "label": city_labels[lang]["karakol"], "cx": 760, "cy": 195},
        {"id": "naryn-city", "label": city_labels[lang]["naryn-city"], "cx": 540, "cy": 295},
    ]


def serialize_ar_marker(marker, lang):
    return {
        "id": marker.id,
        "title": localize_model_value(marker, "title", lang),
        "description": localize_model_value(marker, "description", lang),
        "marker_type": marker.marker_type,
        "marker_type_label": ar_marker_type_label(lang, marker.marker_type),
        "icon": marker.icon,
        "distance_meters": marker.distance_meters,
    }


def serialize_map_landmark(landmark, source, lang):
    region_source = get_region(landmark.region) or {}
    region_name = localize_data_value(region_source, "name", lang) or landmark.region
    has_exact_coordinates = bool(source.get("lat") is not None and source.get("lng") is not None)
    return {
        "id": landmark.id,
        "name": localize_data_value(source, "name", lang) or localize_landmark_value(landmark, "name", lang),
        "description": build_landmark_description(landmark, source, region_name, lang),
        "region_name": region_name,
        "lat": landmark.latitude,
        "lng": landmark.longitude,
        "image_url": image_url(landmark.image),
        "has_image": image_exists(landmark.image),
        "category": landmark.category,
        "category_label": category_label(lang, landmark.category),
        "accessibility_level": landmark.accessibility_level,
        "accessibility_label": accessibility_label(lang, landmark.accessibility_level),
        "physical_intensity": landmark.physical_intensity,
        "physical_label": activity_label(lang, intensity_bucket(landmark.physical_intensity)),
        "recommended_visit_hours": landmark.recommended_visit_hours,
        "is_approximate": not has_exact_coordinates,
        "detail_url": with_lang(reverse("attractions:landmark_detail", args=[landmark.id]), lang),
        "ar_markers": [serialize_ar_marker(marker, lang) for marker in landmark.ar_markers.all()],
    }


def serialize_route_stop(stop, lang):
    landmark = stop["landmark"]
    source = get_landmark_source(landmark)
    region_source = get_region(landmark.region) or {}
    region_name = localize_data_value(region_source, "name", lang) or landmark.region
    return {
        "id": landmark.id,
        "name": localize_data_value(source, "name", lang) or localize_landmark_value(landmark, "name", lang),
        "region_name": region_name,
        "description": build_landmark_description(landmark, source, region_name, lang),
        "image_url": image_url(landmark.image),
        "has_image": image_exists(landmark.image),
        "visit_hours": landmark.recommended_visit_hours,
        "accessibility_label": accessibility_label(lang, landmark.accessibility_level),
        "activity_label": activity_label(lang, intensity_bucket(landmark.physical_intensity)),
        "category_label": category_label(lang, landmark.category),
        "reasons": stop["reasons"],
        "detail_url": with_lang(reverse("attractions:landmark_detail", args=[landmark.id]), lang),
        "lat": landmark.latitude,
        "lng": landmark.longitude,
    }


def home(request):
    lang = prepare_language(request)
    regions = [serialize_region(region, lang) for region in get_all_regions()]
    cities = get_city_markers(lang)

    return render(
        request,
        "attractions/home.html",
        build_context(
            request,
            lang,
            regions=regions,
            regions_json=json.dumps(regions, ensure_ascii=False),
            cities=cities,
        ),
    )


def region_detail(request, region_id):
    lang = prepare_language(request)
    region_source = get_region(region_id)
    if region_source is None:
        raise Http404("Регион не найден")

    sync_region_landmarks(region_id)

    landmarks = (
        Landmark.objects.filter(region=region_id)
        .annotate(
            average_rating=Avg("review__rating"),
            review_count=Count("review", distinct=True),
        )
        .prefetch_related(
            Prefetch(
                "review_set",
                queryset=Review.objects.select_related("user").order_by("-created_at"),
            )
        )
    )

    landmarks_by_name_en = {landmark.name_en: landmark for landmark in landmarks}
    serialized_landmarks = []
    region_name = localize_data_value(region_source, "name", lang)

    for source_landmark in region_source.get("landmarks", []):
        source_name = source_landmark.get("name_en") or source_landmark.get("name") or source_landmark.get("name_ru")
        landmark = landmarks_by_name_en.get(source_name)
        if landmark:
            serialized_landmarks.append(build_landmark_card(landmark, source_landmark, lang, region_name))

    return render(
        request,
        "attractions/region_detail.html",
        build_context(
            request,
            lang,
            region=serialize_region(region_source, lang),
            highlights=get_highlights(region_id, lang),
            landmarks=serialized_landmarks,
        ),
    )


def landmark_detail(request, landmark_id):
    lang = prepare_language(request)
    sync_all_regions()
    landmark = get_object_or_404(Landmark, id=landmark_id)
    source = get_landmark_source(landmark)
    region_source = get_region(landmark.region)
    if region_source is None:
        raise Http404("Регион не найден")

    reviews = landmark.review_set.select_related("user").order_by("-created_at")
    stats = reviews.aggregate(average_rating=Avg("rating"), review_count=Count("id"))
    user_review = reviews.filter(user=request.user).first() if request.user.is_authenticated else None

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(build_auth_link("attractions:login", lang, request.get_full_path()))

        is_new_review = user_review is None
        form = ReviewForm(request.POST, instance=user_review, lang=lang)
        if form.is_valid():
            review = form.save(commit=False)
            review.user = request.user
            review.landmark = landmark
            review.save()
            messages.success(
                request,
                text(lang, "review_success_created" if is_new_review else "review_success_updated"),
            )
            return redirect(with_lang(reverse("attractions:landmark_detail", args=[landmark.id]), lang))
    else:
        form = ReviewForm(instance=user_review, lang=lang) if request.user.is_authenticated else None

    average_rating = stats["average_rating"] or 0
    review_count = stats["review_count"] or 0
    region_name = localize_data_value(region_source, "name", lang)

    landmark_view = {
        "id": landmark.id,
        "name": localize_data_value(source, "name", lang) or localize_landmark_value(landmark, "name", lang),
        "description": build_landmark_description(landmark, source, region_name, lang),
        "image": landmark.image,
        "image_url": image_url(landmark.image),
        "has_image": image_exists(landmark.image),
        "region_name": region_name,
        "average_rating": average_rating,
        "rounded_average": int(round(average_rating)) if average_rating else 0,
        "review_count": review_count,
        "review_word": review_word(lang, review_count),
    }

    return render(
        request,
        "attractions/landmark_detail.html",
        build_context(
            request,
            lang,
            landmark=landmark_view,
            region=serialize_region(region_source, lang),
            reviews=[serialize_review(review) for review in reviews],
            review_form=form,
            rating_options=[1, 2, 3, 4, 5],
            selected_rating=int(form["rating"].value()) if form and form["rating"].value() else 0,
            user_has_review=user_review is not None,
            login_to_review_url=build_auth_link("attractions:login", lang, request.get_full_path()),
            register_to_review_url=build_auth_link("attractions:register", lang, request.get_full_path()),
        ),
    )


def add_review(request, landmark_id):
    lang = prepare_language(request)
    detail_url = f"{with_lang(reverse('attractions:landmark_detail', args=[landmark_id]), lang)}#review-form"
    if request.user.is_authenticated:
        return redirect(detail_url)
    return redirect(build_auth_link("attractions:login", lang, with_lang(reverse("attractions:landmark_detail", args=[landmark_id]), lang)))


def login_view(request):
    lang = prepare_language(request)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = SignInForm(request, data=request.POST, lang=lang)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, text(lang, "login_success", username=user.username))
            return redirect(next_url or with_lang(reverse("attractions:home"), lang))

        messages.error(request, text(lang, "login_error"))
    else:
        form = SignInForm(request, lang=lang)

    return render(
        request,
        "attractions/login.html",
        build_context(request, lang, form=form, next_url=next_url),
    )


def register_view(request):
    lang = prepare_language(request)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = SignUpForm(request.POST, lang=lang)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, text(lang, "register_success", username=user.username))
            return redirect(next_url or with_lang(reverse("attractions:home"), lang))

        messages.error(request, text(lang, "register_error"))
    else:
        form = SignUpForm(lang=lang)

    return render(
        request,
        "attractions/register.html",
        build_context(request, lang, form=form, next_url=next_url),
    )


def logout_view(request):
    lang = prepare_language(request)
    if request.method == "POST":
        logout(request)
    return redirect(with_lang(reverse("attractions:home"), lang))


def interactive_map(request):
    lang = prepare_language(request)
    sync_all_regions()
    landmarks = (
        Landmark.objects.filter(latitude__isnull=False, longitude__isnull=False)
        .prefetch_related(Prefetch("ar_markers", queryset=ARMarker.objects.filter(is_active=True)))
        .order_by("region", "name")
    )
    landmarks_data = [serialize_map_landmark(landmark, get_landmark_source(landmark), lang) for landmark in landmarks]
    map_filters = [
        {"value": "all", "label": text(lang, "map_filter_all")},
        {"value": "history", "label": category_label(lang, "history")},
        {"value": "nature", "label": category_label(lang, "nature")},
        {"value": "culture", "label": category_label(lang, "culture")},
        {"value": "adventure", "label": category_label(lang, "adventure")},
        {"value": "accessible", "label": text(lang, "map_filter_accessible")},
    ]

    return render(
        request,
        "attractions/interactive_map.html",
        build_context(
            request,
            lang,
            map_filters=map_filters,
            landmarks=landmarks_data,
            landmarks_json=json.dumps(landmarks_data, ensure_ascii=False),
            has_approximate_points=any(item["is_approximate"] for item in landmarks_data),
        ),
    )


def generate_route(request):
    lang = prepare_language(request)
    sync_all_regions()
    landmarks = list(Landmark.objects.all().order_by("region", "name"))

    if request.method == "POST":
        form = RouteRequestForm(request.POST, lang=lang)
        if form.is_valid():
            route_plan = recommend_route(landmarks, form.cleaned_data, lang=lang)
            if not route_plan:
                messages.error(request, text(lang, "route_empty_state"))
            else:
                serialized_stops = [serialize_route_stop(stop, lang) for stop in route_plan["stops"]]
                serialized_alternatives = [serialize_route_stop(stop, lang) for stop in route_plan["alternatives"]]
                route_map_points = [
                    {
                        "name": stop["name"],
                        "lat": stop["lat"],
                        "lng": stop["lng"],
                    }
                    for stop in serialized_stops
                    if stop["lat"] is not None and stop["lng"] is not None
                ]
                return render(
                    request,
                    "attractions/route_detail.html",
                    build_context(
                        request,
                        lang,
                        form=form,
                        route_plan={
                            "title": route_plan["title"],
                            "summary": route_plan["summary"],
                            "profile_summary": route_plan["profile_summary"],
                            "difficulty_label": route_plan["difficulty_label"],
                            "selected_regions": route_plan["selected_regions"],
                            "total_hours": route_plan["total_hours"],
                            "stops": serialized_stops,
                            "alternatives": serialized_alternatives,
                        },
                        route_map_points=route_map_points,
                    ),
                )
    else:
        form = RouteRequestForm(lang=lang)

    return render(
        request,
        "attractions/generate_route.html",
        build_context(
            request,
            lang,
            form=form,
        ),
    )
