from typing import Optional, Iterable
from math import exp, sqrt
from .models import HorseEntry, RaceAnalysisSnapshot, EntryAnalysisSnapshot


# =========================
# 基本集計
# =========================

def agari_rank_score(e: HorseEntry) -> Optional[float]:
    """
    過去3走の上がり順位の平均
    小さいほど良い
    """
    ranks = [
        e.last1_agari_rank,
        e.last2_agari_rank,
        e.last3_agari_rank,
    ]
    ranks = [r for r in ranks if r is not None and r > 0]

    if not ranks:
        return None

    return sum(ranks) / len(ranks)


def calc_corner4_index(field_size: int, corner4_pos: int) -> Optional[float]:
    """
    4角位置指数
    ((頭数 - 4角位置) / (頭数 - 1)) × 100
    先頭に近いほど高い
    """
    if not field_size or not corner4_pos:
        return None
    if field_size <= 1:
        return None
    if corner4_pos > field_size:
        return None

    return ((field_size - corner4_pos) / (field_size - 1)) * 100


def _corner4_pairs(entry: HorseEntry):
    return [
        (entry.last1_field_size, entry.last1_corner4_pos),
        (entry.last2_field_size, entry.last2_corner4_pos),
        (entry.last3_field_size, entry.last3_corner4_pos),
    ]


def avg_corner4_index(entry: HorseEntry) -> Optional[float]:
    values = []

    for field_size, pos in _corner4_pairs(entry):
        idx = calc_corner4_index(field_size, pos)
        if idx is not None:
            values.append(idx)

    if not values:
        return None

    return sum(values) / len(values)


def calc_front_metrics(entry: HorseEntry) -> dict:
    """
    4角位置から前受け再現性を分解
    - avg_index: 平均4角位置指数
    - nige_rate: 4角1番手率
    - front3_rate: 4角3番手以内率
    - front5_rate: 4角5番手以内率
    - avg_corner4_pos: 平均4角位置
    - valid_count: 有効レース数
    """
    valid_positions = []
    indices = []

    for field_size, pos in _corner4_pairs(entry):
        if field_size and pos and field_size > 1 and pos <= field_size:
            valid_positions.append(pos)
            idx = calc_corner4_index(field_size, pos)
            if idx is not None:
                indices.append(idx)

    valid_count = len(valid_positions)
    if valid_count == 0:
        return {
            "avg_index": None,
            "nige_rate": 0.0,
            "front3_rate": 0.0,
            "front5_rate": 0.0,
            "avg_corner4_pos": None,
            "valid_count": 0,
        }

    nige_count = sum(1 for pos in valid_positions if pos == 1)
    front3_count = sum(1 for pos in valid_positions if pos <= 3)
    front5_count = sum(1 for pos in valid_positions if pos <= 5)

    return {
        "avg_index": sum(indices) / len(indices) if indices else None,
        "nige_rate": nige_count / valid_count,
        "front3_rate": front3_count / valid_count,
        "front5_rate": front5_count / valid_count,
        "avg_corner4_pos": sum(valid_positions) / valid_count,
        "valid_count": valid_count,
    }


# =========================
# 脚質判定
# =========================

def classify_run_style(entry: HorseEntry) -> str:
    """
    自動脚質判定
    あくまで補助。主役は front5_rate / front3_rate。
    """
    m = calc_front_metrics(entry)
    avg_index = m["avg_index"]
    nige_rate = m["nige_rate"]
    front3_rate = m["front3_rate"]
    front5_rate = m["front5_rate"]

    if avg_index is None:
        return "UNKNOWN"

    if nige_rate >= 0.5:
        return "NIGE"
    if avg_index >= 82 and front3_rate >= 0.67:
        return "NIGE"

    if front5_rate >= 0.67 and avg_index >= 62:
        return "SENKO"

    if front5_rate >= 0.34 and avg_index >= 45:
        return "KOUI"

    if avg_index >= 25:
        return "SASHI"

    return "OIKOMI"


def get_effective_run_style(entry: HorseEntry) -> str:
    """
    自動脚質を優先し、
    出せない場合のみ手入力run_styleへフォールバック
    """
    auto_style = classify_run_style(entry)
    if auto_style != "UNKNOWN":
        return auto_style

    return entry.run_style or "UNKNOWN"


def display_run_style(style_code: str) -> str:
    table = {
        "NIGE": "逃げ",
        "SENKO": "先行",
        "KOUI": "好位",
        "SASHI": "差し",
        "OIKOMI": "追込",
        "UNKNOWN": "不明",
    }
    return table.get(style_code, "不明")


# =========================
# ペース推定
# =========================

def _front_weight(style: str) -> float:
    """
    ペース推定用の前受け圧ウェイト
    """
    return {
        "NIGE": 1.55,
        "SENKO": 1.15,
        "KOUI": 0.65,
        "SASHI": 0.12,
        "OIKOMI": 0.00,
        "UNKNOWN": 0.20,
    }.get(style, 0.20)


def estimate_pace(entries: Iterable[HorseEntry]):
    """
    重み付き前圧でペース推定
    ただし、先行有利思想なので
    差し有利に寄せすぎない判定にする
    """
    entries = list(entries)
    n = len(entries) if entries else 1

    styles = [get_effective_run_style(e) for e in entries]
    pace_pressure = sum(_front_weight(s) for s in styles)
    front_ratio = pace_pressure / n

    n_nige = sum(1 for s in styles if s == "NIGE")
    n_front = sum(1 for s in styles if s in ("NIGE", "SENKO", "KOUI"))

    if n_nige >= 2 and front_ratio >= 0.88:
        pace = "H"
        comment = "逃げ候補が複数いて前圧が高く、やや流れる想定"
    elif front_ratio >= 0.82:
        pace = "H"
        comment = "前圧は高めだが、極端な差し決着までは見込みにくい"
    elif front_ratio >= 0.50:
        pace = "M"
        comment = "先行勢は揃っており、平均ペース想定"
    else:
        pace = "S"
        comment = "前に行く馬が少なく、スロー寄り"

    return pace, comment, round(front_ratio, 3), {
        "n_nige": n_nige,
        "n_front": n_front,
        "pace_pressure": round(pace_pressure, 3),
    }


# =========================
# 指数設計
# =========================

def run_style_point(style: str, pace: str, front_ratio: float) -> float:
    """
    脚質×ペース評価
    差し追込の押し上げをかなり弱め、
    先行残り思想に寄せる
    """
    base = {
        "NIGE": 1.75,
        "SENKO": 1.95,
        "KOUI": 1.65,
        "SASHI": 1.20,
        "OIKOMI": 0.95,
        "UNKNOWN": 1.10,
    }.get(style, 1.10)

    if pace == "S":
        adj = {
            "NIGE": 0.40 - 0.10 * front_ratio,
            "SENKO": 0.34 - 0.08 * front_ratio,
            "KOUI": 0.18 - 0.04 * front_ratio,
            "SASHI": -0.02 + 0.03 * front_ratio,
            "OIKOMI": -0.12 + 0.03 * front_ratio,
            "UNKNOWN": 0.00,
        }
    elif pace == "H":
        adj = {
            "NIGE": -0.22 - 0.10 * front_ratio,
            "SENKO": -0.05 - 0.06 * front_ratio,
            "KOUI": 0.02,
            "SASHI": 0.08 + 0.04 * front_ratio,
            "OIKOMI": 0.06 + 0.03 * front_ratio,
            "UNKNOWN": 0.00,
        }
    else:  # M
        adj = {
            "NIGE": 0.12 - 0.06 * front_ratio,
            "SENKO": 0.18 - 0.04 * front_ratio,
            "KOUI": 0.10,
            "SASHI": 0.02,
            "OIKOMI": -0.04,
            "UNKNOWN": 0.00,
        }

    return base + adj.get(style, 0.0)


def front_keep_score(entry: HorseEntry, pace: str) -> float:
    """
    あなたの理論の中心
    4角1〜5番手に収まる再現性を重く評価する
    """
    m = calc_front_metrics(entry)
    avg_index = m["avg_index"]
    nige_rate = m["nige_rate"]
    front3_rate = m["front3_rate"]
    front5_rate = m["front5_rate"]
    valid_count = m["valid_count"]

    if valid_count == 0 or avg_index is None:
        return -0.40

    score = 0.0

    # 主役：5番手以内率
    score += 2.40 * front5_rate

    # 前3再現性
    score += 1.10 * front3_rate

    # ハナ経験
    score += 0.35 * nige_rate

    # 平均4角位置指数
    score += 0.018 * avg_index

    # データ不足ペナルティ
    if valid_count == 1:
        score -= 0.18
    elif valid_count == 2:
        score -= 0.08

    # ペースによる軽補正
    if pace == "H":
        score -= 0.28 * nige_rate
        score -= 0.10 * max(front3_rate - 0.66, 0.0)
    elif pace == "S":
        score += 0.12 * front3_rate
        score += 0.08 * front5_rate

    return score


def agari_point_relative(avg_rank: Optional[float], field_avg: Optional[float]) -> float:
    """
    上がり順位を平均との差で評価
    ただし今回は補助要素に留める
    """
    if avg_rank is None or field_avg is None:
        return 0.0

    diff = field_avg - avg_rank
    return max(-0.8, min(0.8, 0.22 * diff))


def back_marker_penalty(entry: HorseEntry) -> float:
    """
    後方専用馬への減点
    """
    m = calc_front_metrics(entry)
    avg_index = m["avg_index"]
    front5_rate = m["front5_rate"]

    if avg_index is None:
        return 0.0

    penalty = 0.0

    if front5_rate == 0:
        penalty -= 0.55
    elif front5_rate < 0.34:
        penalty -= 0.20

    if avg_index < 25:
        penalty -= 0.30
    elif avg_index < 35:
        penalty -= 0.12

    return penalty


def senko_value_score(entry: HorseEntry) -> float:
    """
    人気薄でも先行できる馬を評価する
    """
    odds = entry.expected_odds
    if odds is None or odds <= 0:
        return 0.0

    m = calc_front_metrics(entry)
    front5_rate = m["front5_rate"]
    front3_rate = m["front3_rate"]
    avg_index = m["avg_index"]

    if avg_index is None:
        return 0.0

    senko_power = (front5_rate * 0.6) + (front3_rate * 0.3) + (avg_index / 100.0 * 0.1)

    # 先行力が無い人気薄は評価しない
    if senko_power < 0.45:
        if odds >= 40:
            return -0.12
        return 0.0

    if 8.0 <= odds <= 30.0:
        return 0.15 + 0.35 * senko_power
    elif 30.0 < odds <= 60.0:
        return 0.05 + 0.30 * senko_power
    elif odds < 8.0:
        return 0.03
    else:
        return 0.00


def odds_rank_score(odds: Optional[float]) -> float:
    """
    市場補正は弱める
    先行穴評価は senko_value_score 側で行う
    """
    if odds is None or odds <= 0:
        return 0.0

    if odds <= 4.0:
        return 0.10
    elif odds <= 8.0:
        return 0.06
    elif odds <= 15.0:
        return 0.02
    elif odds <= 30.0:
        return 0.00
    elif odds <= 50.0:
        return -0.03
    else:
        return -0.08


# =========================
# 個別スコア
# =========================

def calc_scores(
    entry: HorseEntry,
    pace: str,
    front_ratio: float,
    field_agari_avg: Optional[float]
) -> dict:
    """
    1頭ごとの生スコア
    今回は「勝ち切り」よりも
    3着内・相手向きに寄せたスコア
    """
    avg_agari_rank = agari_rank_score(entry)
    effective_style = get_effective_run_style(entry)
    avg_idx = avg_corner4_index(entry)

    style_score = run_style_point(effective_style, pace, front_ratio)
    front_score = front_keep_score(entry, pace)
    agari_score = agari_point_relative(avg_agari_rank, field_agari_avg)
    odds_score = odds_rank_score(entry.expected_odds)
    senko_hole_score = senko_value_score(entry)
    back_penalty = back_marker_penalty(entry)

    place_fit_raw = (
        front_score * 1.35
        + style_score * 0.75
        + agari_score * 0.45
        + odds_score
        + senko_hole_score
        + back_penalty
    )

    return {
        "tempo_raw": place_fit_raw,
        "tempo": round(place_fit_raw, 2),
        "run_style": effective_style,
        "corner4_index": round(avg_idx, 1) if avg_idx is not None else None,
        "agari_avg_rank": round(avg_agari_rank, 2) if avg_agari_rank is not None else None,

        # デバッグ用
        "front_keep_score": round(front_score, 3),
        "style_score": round(style_score, 3),
        "agari_score": round(agari_score, 3),
        "odds_score": round(odds_score, 3),
        "senko_hole_score": round(senko_hole_score, 3),
        "back_penalty": round(back_penalty, 3),
    }


# =========================
# レース内正規化
# =========================

def _softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    """
    スコアをレース内で疑似確率へ変換
    """
    if not values:
        return []

    scaled = [v / max(temperature, 1e-6) for v in values]
    m = max(scaled)
    exps = [exp(v - m) for v in scaled]
    total = sum(exps)

    if total <= 0:
        n = len(values)
        return [1.0 / n] * n

    return [x / total for x in exps]


def get_longshot_decay(odds: float | None) -> float:
    """
    超人気薄の期待値減衰
    """
    if odds is None:
        return 1.0

    if odds >= 100.0:
        return 0.35
    elif odds >= 60.0:
        return 0.60
    elif odds >= 40.0:
        return 0.80
    else:
        return 1.00


def attach_win_probs(results: list[dict], temperature: float = 1.05) -> list[dict]:
    """
    互換性のため pseudo_win_prob という名前は維持するが、
    実態は「相手候補としての相対評価」に近い
    """
    raw_scores = [r["tempo_raw"] for r in results]
    probs = _softmax(raw_scores, temperature=temperature)

    for r, p in zip(results, probs):
        r["pseudo_win_prob"] = round(p * 100, 1)

        odds = r.get("expected_odds") or 0.0
        front_keep = r.get("front_keep_score", 0.0)
        senko_hole = r.get("senko_hole_score", 0.0)

        if odds > 0:
            base_value = p * sqrt(odds)

            # 先行力がある人気薄は残す
            if front_keep >= 2.2:
                base_value *= 1.08
            if senko_hole >= 0.30:
                base_value *= 1.10

            # 後方専用人気薄の暴れは抑える
            if front_keep < 1.2 and odds >= 20:
                base_value *= 0.75

            decay = get_longshot_decay(odds)
            base_value *= decay

            r["value_index"] = round(base_value, 2)
        else:
            r["value_index"] = None

    return results


# =========================
# レース全体計算
# =========================

def analyze_entries(entries: Iterable[HorseEntry]) -> dict:
    """
    レース全体をまとめて分析
    主眼は「先行できる人気薄の相手候補抽出」
    """
    entries = list(entries)
    if not entries:
        return {
            "pace": "M",
            "pace_comment": "出走馬データがありません",
            "front_ratio": 0.0,
            "meta": {},
            "results": [],
            "field_agari_avg": None,
        }

    pace, pace_comment, front_ratio, meta = estimate_pace(entries)

    agari_values = [agari_rank_score(e) for e in entries]
    agari_values = [x for x in agari_values if x is not None]
    field_agari_avg = sum(agari_values) / len(agari_values) if agari_values else None

    results = []
    for e in entries:
        row = calc_scores(
            entry=e,
            pace=pace,
            front_ratio=front_ratio,
            field_agari_avg=field_agari_avg,
        )
        row["entry"] = e
        row["horse_name"] = getattr(e, "horse_name", None) or str(getattr(e, "horse", ""))
        row["expected_odds"] = e.expected_odds or 0.0
        results.append(row)

    results = attach_win_probs(results)

    # あなたの理論に寄せて、
    # 基本は place_fit_raw 寄り（tempo）で並べる
    results.sort(
        key=lambda x: (
            x["tempo"],
            x["pseudo_win_prob"],
            x["value_index"] if x["value_index"] is not None else -999999,
        ),
        reverse=True,
    )

    return {
        "pace": pace,
        "pace_comment": pace_comment,
        "front_ratio": front_ratio,
        "meta": meta,
        "field_agari_avg": round(field_agari_avg, 2) if field_agari_avg is not None else None,
        "results": results,
    }


# =========================
# 分析結果保存
# =========================

def save_analysis_snapshot(race, analysis, model_version="v2_senko_place"):
    race_snapshot = RaceAnalysisSnapshot.objects.create(
        race=race,
        predicted_pace=analysis["pace"],
        pace_comment=analysis["pace_comment"],
        front_ratio=analysis["front_ratio"],
        n_nige=analysis["meta"].get("n_nige", 0),
        n_front=analysis["meta"].get("n_front", 0),
        pace_pressure=analysis["meta"].get("pace_pressure", 0.0),
        field_agari_avg=analysis["field_agari_avg"],
        model_version=model_version,
    )

    results = analysis["results"]

    sorted_by_prob = sorted(results, key=lambda x: x["pseudo_win_prob"], reverse=True)
    prob_rank_map = {id(r): i for i, r in enumerate(sorted_by_prob, start=1)}

    sorted_by_value = sorted(
        results,
        key=lambda x: x["value_index"] if x["value_index"] is not None else -999999,
        reverse=True,
    )
    value_rank_map = {id(r): i for i, r in enumerate(sorted_by_value, start=1)}

    for r in results:
        e = r["entry"]

        EntryAnalysisSnapshot.objects.create(
            race_snapshot=race_snapshot,
            horse_entry=e,
            horse_name=r["horse_name"],
            horse_number=getattr(e, "number", None),
            gate=getattr(e, "gate", None),
            jockey=getattr(e, "jockey", ""),
            run_style=r["run_style"],
            corner4_index=r["corner4_index"],
            agari_avg_rank=r["agari_avg_rank"],
            tempo_raw=r["tempo_raw"],
            tempo=r["tempo"],
            pseudo_win_prob=r["pseudo_win_prob"],
            value_index=r["value_index"],
            expected_odds=r["expected_odds"],
            rank_by_prob=prob_rank_map[id(r)],
            rank_by_value=value_rank_map[id(r)],
        )

    return race_snapshot