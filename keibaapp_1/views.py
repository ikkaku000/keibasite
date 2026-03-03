from django.shortcuts import render, get_object_or_404
from .models import Race
from .services import calc_scores


def race_db(request):
    # MVP：最新のRaceを1件表示（今週の重賞を入れておけばOK）
    race = Race.objects.order_by("-race_date").first()
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    pace = race.pace or "M"

    rows = []
    for e in race.entries.all().order_by("number"):
        s = calc_scores(e, pace)
        rows.append({
            "horse_name": e.horse_name,
            "style": e.get_run_style_display(),
            "tempo": s["tempo"],
            "ev": s["ev"],
            "odds": e.expected_odds,
        })

    rows_sorted = sorted(rows, key=lambda r: r["ev"], reverse=True)
    for i, r in enumerate(rows_sorted, start=1):
        r["rank"] = i

    return render(request, "keibaapp_1/race_mock.html", {
        "race": {
            "name": race.name,
            "grade": race.grade,
            "course": race.course,
            "pace": pace,
            "pace_comment": race.pace_comment,
        },
        "rows": rows_sorted
    })


def top3_db(request):
    race = Race.objects.order_by("-race_date").first()
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    pace = race.pace or "M"

    rows = []
    for e in race.entries.all():
        s = calc_scores(e, pace)
        rows.append({
            "horse_name": e.horse_name,
            "style": e.get_run_style_display(),
            "tempo": s["tempo"],
            "ev": s["ev"],
            "odds": e.expected_odds,
        })

    rows_sorted = sorted(rows, key=lambda r: r["ev"], reverse=True)[:3]
    for i, r in enumerate(rows_sorted, start=1):
        r["rank"] = i
        # MVP：理由はテンプレ（後でDBに持たせてもOK）
        r["reasons"] = [
            f"想定ペース（{pace}）に脚質が噛み合う",
            "近走の上がり傾向（入力値）を評価",
            "人気薄なら期待値を少し加点（オッズ補正）",
        ]
        r["risks"] = [
            "馬場/展開が想定とズレると評価が変わる",
        ]

    return render(request, "keibaapp_1/top3_mock.html", {
        "race": {
            "name": race.name,
            "grade": race.grade,
            "course": race.course,
            "pace": pace,
            "pace_comment": race.pace_comment,
        },
        "rows": rows_sorted
    })