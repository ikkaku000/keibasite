from django.urls import path
from . import views

urlpatterns = [
    path("", views.top_page, name="top_page"),
    path("race/", views.race_db, name="race_db"),
    path("top/", views.top3_db, name="top3_db"),
]