from django.utils.timezone import now
from django.shortcuts import render, get_object_or_404
from .models import Race
from .services import calc_scores, estimate_pace, convert_to_win_prob, avg_agari_rank


def race_db(request):
    # MVP：最新のRaceを1件表示（今週の重賞を入れておけばOK）
    race = get_current_race()
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    entries = list(race.entries.all())
    pace, pace_comment, front_ratio = estimate_pace(entries)

    # フィールド（出走馬全体）の上がり平均を計算
    agaris = [avg_agari_rank(e) for e in entries]
    agaris = [a for a in agaris if a is not None]
    field_agari_avg = sum(agaris) / len(agaris) if agaris else None

    rows = []
    for e in sorted(entries, key=lambda x: x.number):
        s = calc_scores(e, pace, front_ratio, field_agari_avg)
        rows.append({
            "horse_name": e.horse_name,
            "style": e.get_run_style_display(),
            "tempo": s["tempo"],
            "win_prob": s["win_prob"],
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
            "pace_comment": pace_comment,
        },
        "rows": rows_sorted
    })


def top3_db(request):
    race = get_current_race()
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

def get_current_race():
    today = now().date()

    # 未来のレースで一番近いもの
    upcoming = Race.objects.filter(race_date__gte=today).order_by("race_date").first()
    if upcoming:
        return upcoming

    # なければ直近の過去レース
    return Race.objects.filter(race_date__lt=today).order_by("-race_date").first()