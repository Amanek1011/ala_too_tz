from django.contrib import admin

from .models import ARMarker, Landmark, Review, Route


@admin.register(Landmark)
class LandmarkAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "region",
        "category",
        "accessibility_level",
        "physical_intensity",
        "family_friendly",
    )
    list_filter = ("region", "category", "accessibility_level", "family_friendly", "senior_friendly")
    search_fields = ("name", "name_en", "name_ky", "region")


@admin.register(ARMarker)
class ARMarkerAdmin(admin.ModelAdmin):
    list_display = ("title", "landmark", "marker_type", "distance_meters", "is_active")
    list_filter = ("marker_type", "is_active")
    search_fields = ("title", "landmark__name", "landmark__name_en")


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("name", "difficulty", "duration_hours", "created_by")
    list_filter = ("difficulty",)
    search_fields = ("name", "description")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "landmark", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "landmark__name", "comment")
