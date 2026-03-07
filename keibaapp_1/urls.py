from django.urls import path
from . import views

urlpatterns = [
    path("", views.top_page),
    path("races/", views.races_page, name="races_page"), 
    path("race/", views.race_db),
    path("race/save_snapshot/", views.save_race_snapshot, name="save_race_snapshot"),
    path("top/", views.top3_db),
    path("about/", views.about_page),
]