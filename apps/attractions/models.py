from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class Landmark(models.Model):
    """Модель достопримечательности"""
    name = models.CharField(max_length=200, verbose_name="Название")
    name_en = models.CharField(max_length=200, verbose_name="Name (English)")
    name_ky = models.CharField(max_length=200, verbose_name="Аты (Кыргызча)")
    region = models.CharField(max_length=100, verbose_name="Регион")
    image = models.CharField(max_length=200, blank=True, verbose_name="Изображение")  # Пока используем CharField вместо ImageField
    description = models.TextField(blank=True, verbose_name="Описание")
    description_en = models.TextField(blank=True, verbose_name="Description (English)")
    description_ky = models.TextField(blank=True, verbose_name="Баяндоо (Кыргызча)")

    class Meta:
        verbose_name = "Достопримечательность"
        verbose_name_plural = "Достопримечательности"

    def __str__(self):
        return self.name


class Review(models.Model):
    """Модель отзыва"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    landmark = models.ForeignKey(Landmark, on_delete=models.CASCADE, verbose_name="Достопримечательность")
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Оценка (1-5)"
    )
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        unique_together = ['user', 'landmark']  # Один отзыв на пользователя на достопримечательность

    def __str__(self):
        return f"{self.user.username} - {self.landmark.name} ({self.rating}★)"