from typing import Optional, Iterable
from .models import HorseEntry


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
    """
    if not field_size or not corner4_pos:
        return None
    if field_size <= 1:
        return None
    if corner4_pos > field_size:
        return None

    return ((field_size - corner4_pos) / (field_size - 1)) * 100


def avg_corner4_index(entry: HorseEntry) -> Optional[float]:
    values = []

    pairs = [
        (entry.last1_field_size, entry.last1_corner4_pos),
        (entry.last2_field_size, entry.last2_corner4_pos),
        (entry.last3_field_size, entry.last3_corner4_pos),
    ]

    for field_size, pos in pairs:
        idx = calc_corner4_index(field_size, pos)
        if idx is not None:
            values.append(idx)

    if not values:
        return None

    return sum(values) / len(values)


def classify_run_style_from_index(avg_index: Optional[float]) -> str:
    if avg_index is None:
        return "UNKNOWN"
    if avg_index >= 75:
        return "SENKO"   # 逃げ・先行
    elif avg_index >= 50:
        return "KOUI"    # 好位
    elif avg_index >= 25:
        return "SASHI"   # 差し
    else:
        return "OIKOMI"  # 追込


def get_effective_run_style(entry: HorseEntry) -> str:
    """
    4角位置指数ベースの自動脚質を優先し、
    出せない場合は手入力run_styleを使う
    """
    avg_idx = avg_corner4_index(entry)
    auto_style = classify_run_style_from_index(avg_idx)

    if auto_style != "UNKNOWN":
        return auto_style

    return entry.run_style


def display_run_style(style_code: str) -> str:
    table = {
        "NIGE": "逃げ",
        "SENKO": "逃げ・先行",
        "KOUI": "好位",
        "SASHI": "差し",
        "OIKOMI": "追込",
        "UNKNOWN": "不明",
    }
    return table.get(style_code, "不明")


def run_style_point(style: str, pace: str, front_ratio: float) -> float:
    """
    pace: S / M / H
    front_ratio: 前に行く馬（逃げ・先行・好位）の割合 0〜1
    """
    base = {
        "NIGE": 2.2,
        "SENKO": 2.0,
        "KOUI": 1.9,
        "SASHI": 1.8,
        "OIKOMI": 1.6,
        "UNKNOWN": 1.8,
    }.get(style, 1.8)

    if pace == "S":
        adj = {
            "NIGE": 0.9 - 0.4 * front_ratio,
            "SENKO": 0.6 - 0.3 * front_ratio,
            "KOUI": 0.4 - 0.1 * front_ratio,
            "SASHI": 0.1 + 0.2 * front_ratio,
            "OIKOMI": -0.1 + 0.3 * front_ratio,
            "UNKNOWN": 0.0,
        }
    elif pace == "H":
        adj = {
            "NIGE": -0.2 - 0.3 * front_ratio,
            "SENKO": 0.0 - 0.2 * front_ratio,
            "KOUI": 0.2 + 0.1 * front_ratio,
            "SASHI": 0.5 + 0.3 * front_ratio,
            "OIKOMI": 0.7 + 0.4 * front_ratio,
            "UNKNOWN": 0.1,
        }
    else:
        adj = {
            "NIGE": 0.3 - 0.2 * front_ratio,
            "SENKO": 0.3 - 0.1 * front_ratio,
            "KOUI": 0.3,
            "SASHI": 0.3 + 0.1 * front_ratio,
            "OIKOMI": 0.3 + 0.2 * front_ratio,
            "UNKNOWN": 0.3,
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


def estimate_pace(entries: Iterable[HorseEntry]):
    """
    4角位置指数ベースの自動脚質から前受け率を出してペース推定
    """
    entries = list(entries)
    n = len(entries) if entries else 1

    effective_styles = [get_effective_run_style(e) for e in entries]
    n_front = sum(1 for s in effective_styles if s in ("NIGE", "SENKO", "KOUI"))
    ratio = n_front / n

    if n_front >= 6:
        pace = "H"
        comment = "前に行く馬が多くハイペース寄り"
    elif n_front >= 3:
        pace = "M"
        comment = "平均〜やや速めの想定"
    else:
        pace = "S"
        comment = "前に行く馬が少なくスロー寄り"

    return pace, comment, ratio


def convert_to_win_prob_from_tempo(tempo_score: float) -> float:
    """
    tempoを0〜1に変換（MVP用の疑似勝率）
    """
    x = (tempo_score - 2.5) / 3.0
    x = max(0.05, min(0.60, 0.05 + 0.55 * x))
    return x


def calc_scores(
    entry: HorseEntry,
    pace: str,
    front_ratio: float,
    field_agari_avg: Optional[float]
) -> dict:
    a = avg_agari_rank(entry)

    effective_style = get_effective_run_style(entry)
    avg_idx = avg_corner4_index(entry)

    style_score = run_style_point(effective_style, pace, front_ratio)
    agari_score = agari_point_relative(a, field_agari_avg)

    tempo = style_score + agari_score

    win_prob = convert_to_win_prob_from_tempo(tempo)
    odds = entry.expected_odds or 0.0
    ev = win_prob * odds if odds > 0 else tempo

    return {
        "tempo": round(tempo, 2),
        "win_prob": round(win_prob * 100, 1),
        "ev": round(ev, 2),
        "run_style": effective_style,
        "corner4_index": round(avg_idx, 1) if avg_idx is not None else None,
    }