from typing import Optional, Iterable
from math import exp
from .models import HorseEntry


# =========================
# 基本集計
# =========================

def avg_agari_rank(e: HorseEntry) -> Optional[float]:
    ranks = [e.last1_agari_rank, e.last2_agari_rank, e.last3_agari_rank]
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
    4角位置から前受け再現性を分解して見る
    - avg_index: 平均4角位置指数
    - nige_rate: 4角1番手率
    - front3_rate: 4角3番手以内率
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
            "valid_count": 0,
        }

    nige_count = sum(1 for pos in valid_positions if pos == 1)
    front3_count = sum(1 for pos in valid_positions if pos <= 3)

    return {
        "avg_index": sum(indices) / len(indices) if indices else None,
        "nige_rate": nige_count / valid_count,
        "front3_rate": front3_count / valid_count,
        "valid_count": valid_count,
    }


# =========================
# 脚質判定
# =========================

def classify_run_style(entry: HorseEntry) -> str:
    """
    自動脚質判定の改善版
    平均4角位置指数だけでなく、
    4角1番手率 / 3番手以内率も使って NIGE を分離する
    """
    m = calc_front_metrics(entry)
    avg_index = m["avg_index"]
    nige_rate = m["nige_rate"]
    front3_rate = m["front3_rate"]

    if avg_index is None:
        return "UNKNOWN"

    # 逃げ判定
    # 近3走の中でハナ実績が多い or 前受け再現性が非常に高い
    if nige_rate >= 0.5:
        return "NIGE"
    if avg_index >= 85 and front3_rate >= 0.67:
        return "NIGE"

    # 先行
    if avg_index >= 68:
        return "SENKO"

    # 好位
    if avg_index >= 50:
        return "KOUI"

    # 差し
    if avg_index >= 28:
        return "SASHI"

    # 追込
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
        "NIGE": 1.60,
        "SENKO": 1.10,
        "KOUI": 0.55,
        "SASHI": 0.10,
        "OIKOMI": 0.00,
        "UNKNOWN": 0.20,
    }.get(style, 0.20)


def estimate_pace(entries: Iterable[HorseEntry]):
    """
    改善版ペース推定
    単純人数ではなく、脚質ごとの重み付き合計で判断する
    """
    entries = list(entries)
    n = len(entries) if entries else 1

    styles = [get_effective_run_style(e) for e in entries]
    pace_pressure = sum(_front_weight(s) for s in styles)
    front_ratio = pace_pressure / n

    n_nige = sum(1 for s in styles if s == "NIGE")
    n_front = sum(1 for s in styles if s in ("NIGE", "SENKO", "KOUI"))

    # 逃げ馬が複数いて、前圧も強い
    if n_nige >= 2 and front_ratio >= 0.80:
        pace = "H"
        comment = "逃げ候補が複数いて前圧が強く、ハイペース寄り"
    elif front_ratio >= 0.78:
        pace = "H"
        comment = "前受け圧が高く、ハイペース寄り"
    elif front_ratio >= 0.48:
        pace = "M"
        comment = "先行勢はいるが偏りすぎず、平均ペース想定"
    else:
        pace = "S"
        comment = "前受け圧が弱く、スロー寄り"

    return pace, comment, round(front_ratio, 3), {
        "n_nige": n_nige,
        "n_front": n_front,
        "pace_pressure": round(pace_pressure, 3),
    }


# =========================
# 脚質×ペース評価
# =========================

def run_style_point(style: str, pace: str, front_ratio: float) -> float:
    """
    style, pace, front_ratio から展開評価点を出す
    front_ratio は改善版では「前受け圧に近い値」
    """
    base = {
        "NIGE": 2.20,
        "SENKO": 2.00,
        "KOUI": 1.90,
        "SASHI": 1.80,
        "OIKOMI": 1.60,
        "UNKNOWN": 1.75,
    }.get(style, 1.75)

    if pace == "S":
        adj = {
            "NIGE": 0.90 - 0.35 * front_ratio,
            "SENKO": 0.55 - 0.25 * front_ratio,
            "KOUI": 0.35 - 0.08 * front_ratio,
            "SASHI": 0.05 + 0.18 * front_ratio,
            "OIKOMI": -0.10 + 0.25 * front_ratio,
            "UNKNOWN": 0.00,
        }
    elif pace == "H":
        adj = {
            "NIGE": -0.25 - 0.30 * front_ratio,
            "SENKO": -0.05 - 0.18 * front_ratio,
            "KOUI": 0.18 + 0.08 * front_ratio,
            "SASHI": 0.50 + 0.25 * front_ratio,
            "OIKOMI": 0.70 + 0.30 * front_ratio,
            "UNKNOWN": 0.08,
        }
    else:  # M
        adj = {
            "NIGE": 0.28 - 0.18 * front_ratio,
            "SENKO": 0.28 - 0.08 * front_ratio,
            "KOUI": 0.28,
            "SASHI": 0.28 + 0.08 * front_ratio,
            "OIKOMI": 0.28 + 0.15 * front_ratio,
            "UNKNOWN": 0.20,
        }

    return base + adj.get(style, 0.0)


def agari_point_relative(avg_rank: Optional[float], field_avg: Optional[float]) -> float:
    """
    上がり順位を平均との差で評価
    avg_rank が小さいほど良い（1が最速）
    """
    if avg_rank is None or field_avg is None:
        return 0.0

    diff = field_avg - avg_rank
    return max(-1.2, min(1.2, 0.3 * diff))


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
    1頭ごとの生スコアを計算
    ここではまだ勝率にしない
    """
    a = avg_agari_rank(entry)
    effective_style = get_effective_run_style(entry)
    avg_idx = avg_corner4_index(entry)

    style_score = run_style_point(effective_style, pace, front_ratio)
    agari_score = agari_point_relative(a, field_agari_avg)
    tempo = style_score + agari_score

    return {
        "tempo_raw": tempo,
        "tempo": round(tempo, 2),
        "run_style": effective_style,
        "corner4_index": round(avg_idx, 1) if avg_idx is not None else None,
        "agari_avg_rank": round(a, 2) if a is not None else None,
    }


# =========================
# レース内正規化
# =========================

def _softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    """
    スコアをレース内で疑似勝率へ変換
    temperature を上げると差が縮み、下げると差が広がる
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


def attach_win_probs(results: list[dict], temperature: float = 1.15) -> list[dict]:
    """
    calc_scores() の結果群に対して、レース内で疑似勝率を付与する
    """
    raw_scores = [r["tempo_raw"] for r in results]
    probs = _softmax(raw_scores, temperature=temperature)

    for r, p in zip(results, probs):
        r["pseudo_win_prob"] = round(p * 100, 1)

        odds = r.get("expected_odds") or 0.0

        # 厳密な期待値というより、市場とのズレを見るための妙味指数
        if odds > 0:
            r["value_index"] = round(p * odds, 2)
        else:
            r["value_index"] = None

    return results


# =========================
# レース全体計算
# =========================

def analyze_entries(entries: Iterable[HorseEntry]) -> dict:
    """
    レース全体をまとめて分析するための関数
    View からはまずこれを呼ぶ想定
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

    agari_values = [avg_agari_rank(e) for e in entries]
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

    # 疑似勝率順 → 妙味指数順も使える
    results.sort(key=lambda x: (x["pseudo_win_prob"], x["tempo"]), reverse=True)

    return {
        "pace": pace,
        "pace_comment": pace_comment,
        "front_ratio": front_ratio,
        "meta": meta,
        "field_agari_avg": round(field_agari_avg, 2) if field_agari_avg is not None else None,
        "results": results,
    }