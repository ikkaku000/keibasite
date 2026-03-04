from django.urls import path
from . import views

urlpatterns = [
    path("", views.top_page),     # ← TOPページ
    path("race/", views.race_db),
    path("top/", views.top3_db),
]