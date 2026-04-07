from django.urls import path
from . import views

urlpatterns = [
    path("", views.top_page, name="top_page"),
    path("race/", views.race_db, name="race_db"),
    path("about/", views.about_page, name="about_page"),
    path("races/", views.races_page, name="races_page"),
    path("roi/", views.roi_page, name="roi_page"),
    path("save_snapshot/", views.save_race_snapshot, name="save_race_snapshot"),

    # staff専用
    path("manage/races/", views.race_candidates_page, name="race_candidates_page"),
    path("manage/races/<int:race_id>/feature/", views.set_featured_race, name="set_featured_race"),
]