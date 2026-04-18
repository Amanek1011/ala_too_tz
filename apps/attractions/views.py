import json
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.db.models import Avg, Count, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import activate

from .data import get_all_regions, get_highlights, get_region
from .forms import ReviewForm, SignInForm, SignUpForm
from .models import Landmark, Review
from .translations import (
    LANGUAGE_LABELS,
    get_supported_language,
    get_ui_texts,
    review_word,
    text,
)

IMAGES_DIR = Path(settings.BASE_DIR) / "apps" / "attractions" / "static" / "attractions" / "images"


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


def localize_landmark_value(landmark, field_name, lang):
    language_variants = {
        "ru": [field_name, f"{field_name}_en", f"{field_name}_ky"],
        "en": [f"{field_name}_en", field_name, f"{field_name}_ky"],
        "ky": [f"{field_name}_ky", field_name, f"{field_name}_en"],
    }
    for attr in language_variants[lang]:
        value = getattr(landmark, attr, "")
        if value:
            return value
    return ""


def image_exists(image_name):
    return bool(image_name and (IMAGES_DIR / image_name).exists())


def sync_region_landmarks(region_id):
    region = get_region(region_id)
    if region is None:
        raise Http404("Регион не найден")

    for landmark_data in region.get("landmarks", []):
        english_name = landmark_data.get("name_en") or landmark_data.get("name") or landmark_data.get("name_ru")
        russian_name = landmark_data.get("name_ru") or english_name
        kyrgyz_name = landmark_data.get("name_ky") or russian_name

        landmark = (
            Landmark.objects.filter(region=region_id, name_en=english_name).first()
            or Landmark.objects.filter(region=region_id, name=russian_name).first()
            or Landmark.objects.filter(region=region_id, name=english_name).first()
        )

        payload = {
            "name": russian_name,
            "name_en": english_name,
            "name_ky": kyrgyz_name,
            "region": region_id,
            "image": landmark_data.get("image", ""),
            "description": landmark_data.get("description_ru") or landmark_data.get("description") or "",
            "description_en": landmark_data.get("description_en") or landmark_data.get("description") or "",
            "description_ky": landmark_data.get("description_ky") or landmark_data.get("description_ru") or "",
        }

        if landmark is None:
            Landmark.objects.create(**payload)
            continue

        changed = False
        for field_name, value in payload.items():
            if getattr(landmark, field_name) != value:
                setattr(landmark, field_name, value)
                changed = True
        if changed:
            landmark.save()


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
