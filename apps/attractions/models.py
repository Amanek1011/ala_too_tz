from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

User = get_user_model()


LANDMARK_CATEGORY_CHOICES = [
    ("history", "History"),
    ("nature", "Nature"),
    ("culture", "Culture"),
    ("adventure", "Adventure"),
    ("wellness", "Wellness"),
    ("city", "City"),
]

ACCESSIBILITY_LEVEL_CHOICES = [
    ("full", "Fully accessible"),
    ("partial", "Partially accessible"),
    ("limited", "Limited accessibility"),
]

AR_MARKER_TYPE_CHOICES = [
    ("reconstruction", "Historical reconstruction"),
    ("costume", "Traditional costume"),
    ("story", "Story hotspot"),
    ("panorama", "Panoramic guide"),
]


class Landmark(models.Model):
    """Attraction model."""

    name = models.CharField(max_length=200, verbose_name="Название")
    name_en = models.CharField(max_length=200, verbose_name="Name (English)")
    name_ky = models.CharField(max_length=200, verbose_name="Аты (Кыргызча)")
    region = models.CharField(max_length=100, verbose_name="Регион")
    latitude = models.FloatField(null=True, blank=True, verbose_name="Широта")
    longitude = models.FloatField(null=True, blank=True, verbose_name="Долгота")
    image = models.CharField(max_length=200, blank=True, verbose_name="Изображение")
    description = models.TextField(blank=True, verbose_name="Описание")
    description_en = models.TextField(blank=True, verbose_name="Description (English)")
    description_ky = models.TextField(blank=True, verbose_name="Баяндоо (Кыргызча)")
    category = models.CharField(
        max_length=30,
        choices=LANDMARK_CATEGORY_CHOICES,
        default="culture",
        verbose_name="Category",
    )
    theme_tags = models.JSONField(default=list, blank=True, verbose_name="Theme tags")
    accessibility_level = models.CharField(
        max_length=20,
        choices=ACCESSIBILITY_LEVEL_CHOICES,
        default="partial",
        verbose_name="Accessibility",
    )
    physical_intensity = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Physical intensity",
    )
    family_friendly = models.BooleanField(default=False, verbose_name="Family friendly")
    senior_friendly = models.BooleanField(default=False, verbose_name="Senior friendly")
    recommended_visit_hours = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="Recommended visit duration",
    )

    class Meta:
        verbose_name = "Достопримечательность"
        verbose_name_plural = "Достопримечательности"

    def __str__(self):
        return self.name


class ARMarker(models.Model):
    """Augmented reality overlay anchored to a landmark."""

    landmark = models.ForeignKey(
        Landmark,
        related_name="ar_markers",
        on_delete=models.CASCADE,
        verbose_name="Landmark",
    )
    title = models.CharField(max_length=200, verbose_name="Title")
    title_en = models.CharField(max_length=200, blank=True, verbose_name="Title (English)")
    title_ky = models.CharField(max_length=200, blank=True, verbose_name="Title (Kyrgyz)")
    description = models.TextField(blank=True, verbose_name="Description")
    description_en = models.TextField(blank=True, verbose_name="Description (English)")
    description_ky = models.TextField(blank=True, verbose_name="Description (Kyrgyz)")
    marker_type = models.CharField(
        max_length=30,
        choices=AR_MARKER_TYPE_CHOICES,
        default="story",
        verbose_name="Marker type",
    )
    icon = models.CharField(max_length=30, default="sparkles", verbose_name="Icon name")
    distance_meters = models.PositiveSmallIntegerField(default=20, verbose_name="Distance hint (m)")
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="Sort order")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        verbose_name = "AR marker"
        verbose_name_plural = "AR markers"
        ordering = ("sort_order", "id")

    def __str__(self):
        return f"{self.landmark.name}: {self.title}"


class Route(models.Model):
    """Route model."""

    name = models.CharField(max_length=200, verbose_name="Название маршрута")
    description = models.TextField(blank=True, verbose_name="Описание")
    landmarks = models.ManyToManyField(Landmark, verbose_name="Достопримечательности")
    difficulty = models.CharField(
        max_length=50,
        choices=[("easy", "Легкий"), ("medium", "Средний"), ("hard", "Сложный")],
        default="medium",
        verbose_name="Сложность",
    )
    duration_hours = models.IntegerField(default=1, verbose_name="Длительность (часы)")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Создан пользователем",
    )

    class Meta:
        verbose_name = "Маршрут"
        verbose_name_plural = "Маршруты"

    def __str__(self):
        return self.name


class Review(models.Model):
    """Review model."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    landmark = models.ForeignKey(Landmark, on_delete=models.CASCADE, verbose_name="Достопримечательность")
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Оценка (1-5)",
    )
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        unique_together = ["user", "landmark"]

    def __str__(self):
        return f"{self.user.username} - {self.landmark.name} ({self.rating}★)"
