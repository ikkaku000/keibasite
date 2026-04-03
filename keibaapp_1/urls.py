from django.urls import path
from . import views

urlpatterns = [
    # TOP
    path("", views.top_page, name="top_page"),

    # レース一覧
    path("races/", views.races_page, name="races_page"),

    # 全頭ランキング
    path("race/", views.race_db, name="race_db"),

    # 上位3頭
    path("top/", views.top3_db, name="top3_db"),

    # ロジック説明
    path("about/", views.about_page, name="about_page"),

    # =========================
    # Snapshot保存（重要）
    # =========================
    path("save_snapshot/", views.save_race_snapshot, name="save_race_snapshot"),

    path("roi/", views.roi_page, name="roi_page"),
]