from django.urls import path

from . import views

app_name = 'attractions'

urlpatterns = [
    path('', views.home, name='home'),
    path('region/<slug:region_id>/', views.region_detail, name='region_detail'),
]