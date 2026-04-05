from django.utils.timezone import now
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Prefetch
from datetime import date

from .models import (
    Race,
    RaceAnalysisSnapshot,
    EntryAnalysisSnapshot,
    EntryResultSnapshot,
)
from .services import (
    display_run_style,
    analyze_entries,
    save_analysis_snapshot,
)


MODEL_VERSION = "v3_front_keep_place"


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
        "meta": analysis.get("meta", {}),
    }


def build_row_data(results, limit=None):
    """
    analysis["results"] をテンプレート表示用の rows に変換
    """
    # 先に全件から妙味指数トップを判定
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

            # 新ロジック対応
            "place_label": r.get("place_label"),
            "reason": r.get("reason"),
            "data_confidence": r.get("data_confidence"),
            "is_best_ev": (best_ev is not None and ev == best_ev),

            # front_metrics 展開表示用
            "front5_rate": round(front_metrics.get("front5_rate", 0.0) * 100, 1),
            "front3_rate": round(front_metrics.get("front3_rate", 0.0) * 100, 1),
            "nige_rate": round(front_metrics.get("nige_rate", 0.0) * 100, 1),
            "avg_corner4_pos": front_metrics.get("avg_corner4_pos"),
            "std_corner4_pos": front_metrics.get("std_corner4_pos"),
            "consistency": round(front_metrics.get("consistency", 0.0) * 100, 1),
            "valid_count": front_metrics.get("valid_count", 0),

            # デバッグ / 詳細表示用
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


def maybe_auto_save_snapshot(request, race, analysis, model_version=MODEL_VERSION):
    """
    Snapshot自動保存
    - DEBUG=True の開発環境、または staff ユーザーのみ有効
    - 同じ race × model_version が既にあれば新規保存しない
    - ?force_snapshot=1 を付けると強制保存
    """
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


def top_page(request):
    from datetime import date

    race = get_current_race()
    cutoff_date = date(2026, 4, 5)  # ← 大阪杯

    snapshots = (
        EntryAnalysisSnapshot.objects
        .select_related("race_snapshot", "race_snapshot__race")
        .prefetch_related("result_snapshot")
        .filter(race_snapshot__race__race_date__gte=cutoff_date)
        .order_by("race_snapshot__race__race_date")
    )

    race_map = {}

    for row in snapshots:
        rs = row.race_snapshot
        rid = rs.id

        if rid not in race_map:
            race_map[rid] = []

        race_map[rid].append(row)

    labels = []
    roi_values = []

    total_bet = 0
    total_return = 0

    for rid, rows in race_map.items():
        rows_sorted = sorted(rows, key=lambda x: x.rank_by_prob or 999)

        if not rows_sorted:
            continue

        honmei = rows_sorted[0]
        result = getattr(honmei, "result_snapshot", None)

        bet = 100
        ret = result.place_payoff if result and result.place_payoff else 0

        total_bet += bet
        total_return += ret

        roi = int((total_return / total_bet) * 100) if total_bet else 0

        labels.append(honmei.race_snapshot.race.name)
        roi_values.append(roi)

    return render(request, "keibaapp_1/top.html", {
        "race": race,
        "chart_labels": labels,
        "chart_roi": roi_values,
        "total_roi": int((total_return / total_bet) * 100) if total_bet else 0,
        "race_count": len(labels),
    })


def about_page(request):
    return render(request, "keibaapp_1/about.html")


def races_page(request):
    cutoff_date = date(2026, 4, 5)  # ← 大阪杯の日に変更

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

        honmei = (
            EntryAnalysisSnapshot.objects
            .filter(race_snapshot=snapshot, rank_by_prob=1)
            .first()
        )

        result = getattr(honmei, "result_snapshot", None) if honmei else None

        bet = 100
        payoff = result.place_payoff if result and result.place_payoff else 0
        roi = int((payoff / bet) * 100) if payoff else 0

        data.append({
            "id": race.id,
            "name": race.name,
            "race_date": race.race_date,
            "honmei": honmei.horse_name if honmei else "-",
            "rank": result.rank if result else None,
            "place_payoff": payoff,
            "roi": roi,
        })

    return render(request, "keibaapp_1/races.html", {
        "races": data
    })


def race_db(request):
    """
    全頭ランキング表示ページ
    運営側が開いたときのみSnapshotを自動保存
    """
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

    context = {
        "race": build_race_context(race, analysis),
        "rows": build_row_data(analysis["results"]),
        "analysis": analysis,
        "debug": settings.DEBUG,
        "snapshot_id": snapshot.id if snapshot else None,
        "snapshot_created": snapshot_created,
        "snapshot_status": snapshot_status,
        "model_version": MODEL_VERSION,
    }
    return render(request, "keibaapp_1/race_mock.html", context)


def top3_db(request):
    """
    上位3頭表示ページ
    こちらでは自動保存しない
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
        "debug": settings.DEBUG,
        "model_version": MODEL_VERSION,
    }
    return render(request, "keibaapp_1/top3_mock.html", context)


@staff_member_required
def save_race_snapshot(request):
    """
    手動保存用
    /save_snapshot/?race_id=1
    """
    race = get_selected_or_current_race(request)
    if not race:
        return HttpResponse("race not found")

    entries = list(race.entries.all())
    analysis = analyze_entries(entries)
    snapshot = save_analysis_snapshot(race, analysis, model_version=MODEL_VERSION)

    return HttpResponse(f"saved snapshot id={snapshot.id}")


def roi_page(request):
    """
    Snapshotベースの簡易回収率ページ

    - 集計対象: EntryResultSnapshot が入っているもの
    - strategy:
        prob1       = 疑似確率1位を単勝100円で買った想定
        value1      = 妙味順位1位を単勝100円で買った想定
        top3_place  = 疑似確率上位3頭を複勝100円ずつ買った想定
    """
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

    # レース単位にまとめる
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

    # 集計用
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

        # 疑似確率1位 単勝100円
        if prob1 and hasattr(prob1, "result_snapshot"):
            race_prob1_bet += 100
            if prob1.result_snapshot and prob1.result_snapshot.win_payoff:
                race_prob1_return += prob1.result_snapshot.win_payoff

        # 妙味1位 単勝100円
        if value1 and hasattr(value1, "result_snapshot"):
            race_value1_bet += 100
            if value1.result_snapshot and value1.result_snapshot.win_payoff:
                race_value1_return += value1.result_snapshot.win_payoff

        # 疑似確率上位3頭 複勝100円ずつ
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