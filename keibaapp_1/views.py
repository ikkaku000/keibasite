from django.utils.timezone import now
from django.shortcuts import render, get_object_or_404
from .models import Race
from .services import calc_scores, estimate_pace, avg_agari_rank, display_run_style, analyze_entries


def race_db(request):
    race = get_selected_or_current_race(request)
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)

    rows = []
    for i, r in enumerate(analysis["results"], start=1):
        rows.append({
            "rank": i,
            "horse_name": r["horse_name"],
            "style": display_run_style(r["run_style"]),
            "corner4_index": r["corner4_index"],
            "tempo": r["tempo"],
            "win_prob": r["pseudo_win_prob"],   # ← 新名称
            "ev": r["value_index"],             # ← 新名称
            "odds": r["expected_odds"],
        })

    return render(request, "keibaapp_1/race_mock.html", {
        "race": {
            "name": race.name,
            "grade": race.grade,
            "course": race.course,
            "pace": analysis["pace"],
            "pace_comment": analysis["pace_comment"],
        },
        "rows": rows
    })

def top3_db(request):
    race = get_selected_or_current_race(request)
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)

    rows_sorted = analysis["results"][:3]

    rows = []
    for i, r in enumerate(rows_sorted, start=1):
        rows.append({
            "rank": i,
            "horse_name": r["horse_name"],
            "style": display_run_style(r["run_style"]),
            "corner4_index": r["corner4_index"],
            "tempo": r["tempo"],
            "win_prob": r["pseudo_win_prob"],
            "ev": r["value_index"],
            "odds": r["expected_odds"],
        })

    return render(request, "keibaapp_1/top3_mock.html", {
        "race": {
            "name": race.name,
            "grade": race.grade,
            "course": race.course,
            "pace": analysis["pace"],
            "pace_comment": analysis["pace_comment"],
        },
        "rows": rows
    })

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

    #Topページ
def top_page(request):
    race = get_current_race()
    return render(request, "keibaapp_1/top.html", {
        "race": race,
    })

    #Aboutページ
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