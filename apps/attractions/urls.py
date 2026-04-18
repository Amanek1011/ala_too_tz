from django.urls import path

from . import views

app_name = 'attractions'

urlpatterns = [
    path('', views.home, name='home'),
    path('region/<slug:region_id>/', views.region_detail, name='region_detail'),
    path('landmark/<int:landmark_id>/', views.landmark_detail, name='landmark_detail'),
    path('landmark/<int:landmark_id>/review/', views.add_review, name='add_review'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('map/', views.interactive_map, name='interactive_map'),
    path('generate-route/', views.generate_route, name='generate_route'),
]
