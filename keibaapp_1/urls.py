from django.urls import path
from . import views

urlpatterns = [
    path("", views.race_db, name="race_db"),
    path("top/", views.top3_db, name="top3_db"),
]