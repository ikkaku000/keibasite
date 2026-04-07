from datetime import date

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now

from .models import (
    EntryAnalysisSnapshot,
    EntryResultSnapshot,
    Race,
    RaceAnalysisSnapshot,
)
from .services import (
    analyze_entries,
    display_run_style,
    save_analysis_snapshot,
)


MODEL_VERSION = "v3_front_keep_place"


def get_featured_race():
    return (
        Race.objects
        .filter(is_featured_this_week=True)
        .order_by("race_date", "id")
        .first()
    )


def get_current_race():
    today = now().date()

    upcoming = Race.objects.filter(race_date__gte=today).order_by("race_date").first()
    if upcoming:
        return upcoming

    return Race.objects.filter(race_date__lt=today).order_by("-race_date").first()


def get_selected_or_current_race(request):
    race_id = request.GET.get("race_id")
    if race_id:
        return get_object_or_404(Race, id=race_id)

    featured = get_featured_race()
    if featured:
        return featured

    return get_current_race()


def build_race_context(race, analysis):
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
        "meta": analysis.get("meta", {}),
    }


def build_row_data(results, limit=None):
    valid_evs = [
        r.get("value_index")
        for r in results
        if r.get("value_index") is not None
    ]
    best_ev = max(valid_evs) if valid_evs else None

    all_rows = []
    for i, r in enumerate(results, start=1):
        front_metrics = r.get("front_metrics", {}) or {}
        ev = r.get("value_index")

        all_rows.append({
            "rank": i,
            "horse_name": r["horse_name"],
            "style": display_run_style(r["run_style"]),
            "run_style_code": r["run_style"],
            "corner4_index": r.get("corner4_index"),
            "agari_avg_rank": r.get("agari_avg_rank"),
            "tempo": r["tempo"],
            "tempo_raw": r.get("tempo_raw"),
            "win_prob": r.get("pseudo_win_prob"),
            "ev": ev,
            "odds": r.get("expected_odds"),
            "place_label": r.get("place_label"),
            "reason": r.get("reason"),
            "data_confidence": r.get("data_confidence"),
            "is_best_ev": (best_ev is not None and ev == best_ev),
            "front5_rate": round(front_metrics.get("front5_rate", 0.0) * 100, 1),
            "front3_rate": round(front_metrics.get("front3_rate", 0.0) * 100, 1),
            "nige_rate": round(front_metrics.get("nige_rate", 0.0) * 100, 1),
            "avg_corner4_pos": front_metrics.get("avg_corner4_pos"),
            "std_corner4_pos": front_metrics.get("std_corner4_pos"),
            "consistency": round(front_metrics.get("consistency", 0.0) * 100, 1),
            "valid_count": front_metrics.get("valid_count", 0),
            "front_keep_score": r.get("front_keep_score"),
            "style_score": r.get("style_score"),
            "pace_resilience_score": r.get("pace_resilience_score"),
            "agari_score": r.get("agari_score"),
            "odds_score": r.get("odds_score"),
            "senko_hole_score": r.get("senko_hole_score"),
            "back_penalty": r.get("back_penalty"),
        })

    if limit is not None:
        return all_rows[:limit]

    return all_rows


def build_featured_rows(rows):
    if not rows:
        return []

    featured = []

    top_row = rows[0]
    featured.append({
        **top_row,
        "featured_title": "前残り本命候補",
    })

    best_ev_row = next((r for r in rows if r.get("is_best_ev")), None)

    if best_ev_row and best_ev_row["horse_name"] != top_row["horse_name"]:
        featured.append({
            **best_ev_row,
            "featured_title": "前残り期待値1位",
        })

    return featured


def maybe_auto_save_snapshot(request, race, analysis, model_version=MODEL_VERSION):
    is_operator = settings.DEBUG or (
        request.user.is_authenticated and request.user.is_staff
    )

    if not is_operator:
        return None, False, "not_allowed"

    force_save = request.GET.get("force_snapshot") == "1"

    latest = (
        RaceAnalysisSnapshot.objects
        .filter(race=race, model_version=model_version)
        .order_by("-calculated_at")
        .first()
    )

    if latest and not force_save:
        return latest, False, "already_exists"

    snapshot = save_analysis_snapshot(race, analysis, model_version=model_version)
    return snapshot, True, "created"


def get_race_result_amounts(snapshot):
    race_result = getattr(snapshot, "race_result", None)
    if not race_result:
        return 0, 0

    bet = race_result.bet_amount or 0
    ret = race_result.return_amount or 0
    return bet, ret


def top_page(request):
    race = get_featured_race() or get_current_race()
    cutoff_date = date(2026, 4, 5)

    race_snapshots = (
        RaceAnalysisSnapshot.objects
        .select_related("race")
        .prefetch_related("race_result")
        .filter(race__race_date__gte=cutoff_date)
        .order_by("race_id", "-calculated_at")
    )

    latest_snapshots = {}
    for snapshot in race_snapshots:
        race_id = snapshot.race.id
        if race_id not in latest_snapshots:
            latest_snapshots[race_id] = snapshot

    labels = []
    roi_values = []
    total_bet = 0
    total_return = 0

    ordered_snapshots = sorted(
        latest_snapshots.values(),
        key=lambda s: (s.race.race_date, s.race.id)
    )

    for snapshot in ordered_snapshots:
        bet, ret = get_race_result_amounts(snapshot)

        if bet <= 0:
            continue

        total_bet += bet
        total_return += ret

        roi = int((total_return / total_bet) * 100) if total_bet else 0

        labels.append(snapshot.race.name)
        roi_values.append(roi)

    total_profit = total_return - total_bet

    return render(request, "keibaapp_1/top.html", {
        "race": race,
        "chart_labels": labels,
        "chart_roi": roi_values,
        "total_roi": int((total_return / total_bet) * 100) if total_bet else 0,
        "total_bet": total_bet,
        "total_return": total_return,
        "total_profit": total_profit,
        "race_count": len(labels),
    })


def about_page(request):
    return render(request, "keibaapp_1/about.html")


def races_page(request):
    cutoff_date = date(2026, 4, 5)

    races = (
        Race.objects
        .filter(race_date__gte=cutoff_date)
        .order_by("-race_date")
    )

    data = []

    for race in races:
        snapshot = (
            RaceAnalysisSnapshot.objects
            .filter(race=race)
            .order_by("-calculated_at")
            .first()
        )

        if not snapshot:
            continue

        value1 = (
            EntryAnalysisSnapshot.objects
            .filter(race_snapshot=snapshot, rank_by_value=1)
            .select_related("result_snapshot")
            .first()
        )

        result = getattr(value1, "result_snapshot", None) if value1 else None
        bet, ret = get_race_result_amounts(snapshot)
        roi = int((ret / bet) * 100) if bet else 0
        profit = ret - bet

        data.append({
            "id": race.id,
            "name": race.name,
            "race_date": race.race_date,
            "honmei": value1.horse_name if value1 else "-",
            "rank": result.finish_position if result else None,
            "bet_amount": bet,
            "return_amount": ret,
            "profit": profit,
            "roi": roi,
        })

    return render(request, "keibaapp_1/races.html", {
        "races": data
    })


def race_db(request):
    race = get_selected_or_current_race(request)
    if not race:
        return render(request, "keibaapp_1/race_empty.html")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)

    snapshot, snapshot_created, snapshot_status = maybe_auto_save_snapshot(
        request=request,
        race=race,
        analysis=analysis,
        model_version=MODEL_VERSION,
    )

    row_data = build_row_data(analysis["results"])
    featured_rows = build_featured_rows(row_data)

    context = {
        "race": build_race_context(race, analysis),
        "rows": row_data,
        "featured_rows": featured_rows,
        "analysis": analysis,
        "debug": settings.DEBUG,
        "snapshot_id": snapshot.id if snapshot else None,
        "snapshot_created": snapshot_created,
        "snapshot_status": snapshot_status,
        "model_version": MODEL_VERSION,
    }
    return render(request, "keibaapp_1/race_mock.html", context)


@staff_member_required
def save_race_snapshot(request):
    race = get_selected_or_current_race(request)
    if not race:
        return HttpResponse("race not found")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)
    snapshot = save_analysis_snapshot(race, analysis, model_version=MODEL_VERSION)

    return HttpResponse(f"saved snapshot id={snapshot.id}")


@staff_member_required
def race_candidates_page(request):
    races = (
        Race.objects
        .all()
        .order_by("-race_date", "id")
    )

    featured_race = get_featured_race()

    return render(request, "keibaapp_1/race_candidates.html", {
        "races": races,
        "featured_race": featured_race,
    })


@staff_member_required
def set_featured_race(request, race_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    selected_race = get_object_or_404(Race, id=race_id)

    with transaction.atomic():
        Race.objects.filter(is_featured_this_week=True).update(is_featured_this_week=False)
        selected_race.is_featured_this_week = True
        selected_race.save(update_fields=["is_featured_this_week"])

    return redirect("race_candidates_page")


def roi_page(request):
    model_version = request.GET.get("model_version", MODEL_VERSION)

    snapshots = (
        EntryAnalysisSnapshot.objects
        .filter(race_snapshot__model_version=model_version)
        .select_related("race_snapshot", "race_snapshot__race")
        .prefetch_related(
            Prefetch(
                "result_snapshot",
                queryset=EntryResultSnapshot.objects.all()
            )
        )
        .order_by("race_snapshot__race__race_date", "race_snapshot__id", "rank_by_prob")
    )

    race_map = {}
    for row in snapshots:
        race_snapshot = row.race_snapshot
        rs_id = race_snapshot.id

        if rs_id not in race_map:
            race_map[rs_id] = {
                "snapshot": race_snapshot,
                "rows": [],
            }
        race_map[rs_id]["rows"].append(row)

    race_blocks = list(race_map.values())

    prob1_bet = 0
    prob1_return = 0

    value1_bet = 0
    value1_return = 0

    top3_place_bet = 0
    top3_place_return = 0

    detail_rows = []
    chart_labels = []
    chart_prob1_roi = []
    chart_value1_roi = []
    chart_top3_place_roi = []

    cum_prob1_bet = 0
    cum_prob1_return = 0
    cum_value1_bet = 0
    cum_value1_return = 0
    cum_top3_place_bet = 0
    cum_top3_place_return = 0

    for block in race_blocks:
        snapshot = block["snapshot"]
        rows = block["rows"]

        rows_by_prob = sorted(
            rows,
            key=lambda x: (x.rank_by_prob if x.rank_by_prob is not None else 9999)
        )
        rows_by_value = sorted(
            rows,
            key=lambda x: (x.rank_by_value if x.rank_by_value is not None else 9999)
        )

        prob1 = rows_by_prob[0] if rows_by_prob else None
        value1 = rows_by_value[0] if rows_by_value else None
        top3 = rows_by_prob[:3]

        race_prob1_bet = 0
        race_prob1_return = 0

        race_value1_bet = 0
        race_value1_return = 0

        race_top3_place_bet = 0
        race_top3_place_return = 0

        if prob1 and hasattr(prob1, "result_snapshot"):
            race_prob1_bet += 100
            if prob1.result_snapshot and prob1.result_snapshot.win_payoff:
                race_prob1_return += prob1.result_snapshot.win_payoff

        if value1 and hasattr(value1, "result_snapshot"):
            race_value1_bet += 100
            if value1.result_snapshot and value1.result_snapshot.win_payoff:
                race_value1_return += value1.result_snapshot.win_payoff

        valid_top3_count = 0
        for r in top3:
            if hasattr(r, "result_snapshot"):
                valid_top3_count += 1
                if r.result_snapshot and r.result_snapshot.place_payoff:
                    race_top3_place_return += r.result_snapshot.place_payoff

        if valid_top3_count > 0:
            race_top3_place_bet += valid_top3_count * 100

        prob1_bet += race_prob1_bet
        prob1_return += race_prob1_return

        value1_bet += race_value1_bet
        value1_return += race_value1_return

        top3_place_bet += race_top3_place_bet
        top3_place_return += race_top3_place_return

        cum_prob1_bet += race_prob1_bet
        cum_prob1_return += race_prob1_return
        cum_value1_bet += race_value1_bet
        cum_value1_return += race_value1_return
        cum_top3_place_bet += race_top3_place_bet
        cum_top3_place_return += race_top3_place_return

        prob1_roi = round((cum_prob1_return / cum_prob1_bet) * 100, 1) if cum_prob1_bet else 0
        value1_roi = round((cum_value1_return / cum_value1_bet) * 100, 1) if cum_value1_bet else 0
        top3_place_roi = round((cum_top3_place_return / cum_top3_place_bet) * 100, 1) if cum_top3_place_bet else 0

        chart_labels.append(f"{snapshot.race.race_date:%m/%d} {snapshot.race.name}")
        chart_prob1_roi.append(prob1_roi)
        chart_value1_roi.append(value1_roi)
        chart_top3_place_roi.append(top3_place_roi)

        detail_rows.append({
            "race_date": snapshot.race.race_date,
            "race_name": snapshot.race.name,
            "grade": snapshot.race.grade,
            "pace": snapshot.predicted_pace,
            "prob1_name": prob1.horse_name if prob1 else "-",
            "prob1_return": race_prob1_return,
            "value1_name": value1.horse_name if value1 else "-",
            "value1_return": race_value1_return,
            "top3_place_return": race_top3_place_return,
        })

    summary = {
        "model_version": model_version,
        "race_count": len(race_blocks),
        "prob1_bet": prob1_bet,
        "prob1_return": prob1_return,
        "prob1_roi": round((prob1_return / prob1_bet) * 100, 1) if prob1_bet else 0,
        "value1_bet": value1_bet,
        "value1_return": value1_return,
        "value1_roi": round((value1_return / value1_bet) * 100, 1) if value1_bet else 0,
        "top3_place_bet": top3_place_bet,
        "top3_place_return": top3_place_return,
        "top3_place_roi": round((top3_place_return / top3_place_bet) * 100, 1) if top3_place_bet else 0,
    }

    return render(request, "keibaapp_1/roi.html", {
        "summary": summary,
        "detail_rows": detail_rows,
        "chart_labels": chart_labels,
        "chart_prob1_roi": chart_prob1_roi,
        "chart_value1_roi": chart_value1_roi,
        "chart_top3_place_roi": chart_top3_place_roi,
        "model_version": model_version,
    })