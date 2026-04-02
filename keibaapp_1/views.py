from django.utils.timezone import now
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse

from .models import Race
from .services import (
    display_run_style,
    analyze_entries,
    save_analysis_snapshot,
)


def get_current_race():
    today = now().date()

    # 未来のレースで一番近いもの
    upcoming = Race.objects.filter(race_date__gte=today).order_by("race_date").first()
    if upcoming:
        return upcoming

    # なければ直近の過去レース
    return Race.objects.filter(race_date__lt=today).order_by("-race_date").first()


def get_selected_or_current_race(request):
    race_id = request.GET.get("race_id")
    if race_id:
        return get_object_or_404(Race, id=race_id)
    return get_current_race()


def build_race_context(race, analysis):
    """
    テンプレートへ渡す race 情報を統一
    """
    return {
        "id": race.id,
        "name": race.name,
        "grade": race.grade,
        "course": race.course,
        "race_date": race.race_date,
        "pace": analysis["pace"],
        "pace_comment": analysis["pace_comment"],
        "front_ratio": analysis.get("front_ratio"),
        "field_agari_avg": analysis.get("field_agari_avg"),
        "field_agari_3f_avg": analysis.get("field_agari_3f_avg"),
        "meta": analysis.get("meta", {}),
    }


def build_row_data(results, limit=None):
    """
    analysis["results"] をテンプレート表示用の rows に変換
    """
    if limit is not None:
        results = results[:limit]

    rows = []
    for i, r in enumerate(results, start=1):
        rows.append({
            "rank": i,
            "horse_name": r["horse_name"],
            "style": display_run_style(r["run_style"]),
            "corner4_index": r["corner4_index"],
            "agari_avg_rank": r.get("agari_avg_rank"),
            "agari_avg_3f": r.get("agari_avg_3f"),
            "tempo": r["tempo"],
            "win_prob": r["pseudo_win_prob"],
            "ev": r["value_index"],
            "odds": r["expected_odds"],
            # 必要に応じてテンプレートで使えるよう残しておく
            "style_score": r.get("style_score"),
            "agari_rank_rel": r.get("agari_rank_rel"),
            "agari_3f_rel": r.get("agari_3f_rel"),
            "ability_score": r.get("ability_score"),
            "jockey_score": r.get("jockey_score"),
            "gate_score": r.get("gate_score"),
        })
    return rows


def top_page(request):
    race = get_current_race()
    return render(request, "keibaapp_1/top.html", {
        "race": race,
    })


def about_page(request):
    return render(request, "keibaapp_1/about.html")


def races_page(request):
    today = now().date()

    upcoming = Race.objects.filter(race_date__gte=today).order_by("race_date")[:20]
    recent = Race.objects.filter(race_date__lt=today).order_by("-race_date")[:20]

    return render(request, "keibaapp_1/races.html", {
        "upcoming": upcoming,
        "recent": recent,
        "today": today,
    })


def race_db(request):
    """
    全頭ランキング表示ページ
    """
    race = get_selected_or_current_race(request)
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)

    context = {
        "race": build_race_context(race, analysis),
        "rows": build_row_data(analysis["results"]),
        "analysis": analysis,
    }
    return render(request, "keibaapp_1/race_mock.html", context)


def top3_db(request):
    """
    上位3頭表示ページ
    """
    race = get_selected_or_current_race(request)
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)

    context = {
        "race": build_race_context(race, analysis),
        "rows": build_row_data(analysis["results"], limit=3),
        "analysis": analysis,
    }
    return render(request, "keibaapp_1/top3_mock.html", context)


def save_race_snapshot(request):
    """
    現在の分析結果を保存
    """
    race = get_selected_or_current_race(request)
    if not race:
        return HttpResponse("race not found")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)
    snapshot = save_analysis_snapshot(race, analysis, model_version="v2")

    return HttpResponse(f"saved snapshot id={snapshot.id}")