from typing import Optional, Iterable
from .models import HorseEntry


def avg_agari_rank(e: HorseEntry) -> Optional[float]:
    ranks = [e.last1_agari_rank, e.last2_agari_rank, e.last3_agari_rank]
    ranks = [r for r in ranks if r is not None and r > 0]
    if not ranks:
        return None
    return sum(ranks) / len(ranks)


def run_style_point(style: str, pace: str, front_ratio: float) -> float:
    """
    pace: S/M/H
    front_ratio: 逃げ先行の割合（0〜1）
    """
    # ベース点（ざっくり）
    base = {
        "NIGE": 2.2,
        "SENKO": 2.0,
        "SASHI": 1.8,
        "OIKOMI": 1.6,
        "UNKNOWN": 1.8,
    }.get(style, 1.8)

    # ペース補正（今までの思想を保ちつつ滑らかに）
    if pace == "S":
        # 前有利。前が多いほど価値は少し落ちる
        adj = {
            "NIGE": 0.9 - 0.4 * front_ratio,
            "SENKO": 0.6 - 0.3 * front_ratio,
            "SASHI": 0.1 + 0.2 * front_ratio,
            "OIKOMI": -0.1 + 0.3 * front_ratio,
            "UNKNOWN": 0.0,
        }
    elif pace == "H":
        # 差し追込有利。前が多いほど差しが有利になりやすい
        adj = {
            "NIGE": -0.2 - 0.3 * front_ratio,
            "SENKO": 0.0 - 0.2 * front_ratio,
            "SASHI": 0.5 + 0.3 * front_ratio,
            "OIKOMI": 0.7 + 0.4 * front_ratio,
            "UNKNOWN": 0.1,
        }
    else:
        # Mは中間
        adj = {
            "NIGE": 0.3 - 0.2 * front_ratio,
            "SENKO": 0.3 - 0.1 * front_ratio,
            "SASHI": 0.3 + 0.1 * front_ratio,
            "OIKOMI": 0.3 + 0.2 * front_ratio,
            "UNKNOWN": 0.3,
        }

    return base + adj.get(style, 0.0)


def agari_point(avg_rank: Optional[float]) -> float:
    if avg_rank is None:
        return 1.0
    if avg_rank <= 1:
        return 3.0
    if avg_rank <= 5:
        return 2.0
    if avg_rank <= 10:
        return 1.0
    return 0.5

def agari_point_relative(avg_rank: Optional[float], field_avg: Optional[float]) -> float:
    """
    上がり順位を平均との差で評価
    avg_rank が小さいほど良い（1が最速）
    """
    if avg_rank is None or field_avg is None:
        return 0.0

    diff = field_avg - avg_rank  # プラスなら平均より良い

    # diff が +3 なら +0.9、-3 なら -0.9 くらいの感覚
    return max(-1.2, min(1.2, 0.3 * diff))


def odds_bonus(odds: Optional[float]) -> float:
    if odds is None or odds <= 0:
        return 1.0
    if odds >= 20:
        return 1.25
    if odds >= 10:
        return 1.15
    if odds >= 5:
        return 1.05
    return 1.0


def calc_scores(entry: HorseEntry, pace: str, front_ratio: float, field_agari_avg: Optional[float]) -> dict:
    a = avg_agari_rank(entry)

    style_score = run_style_point(entry.run_style, pace, front_ratio)
    agari_score = agari_point_relative(a, field_agari_avg)

    tempo = style_score + agari_score  # 新しい展開指数

    win_prob = convert_to_win_prob_from_tempo(tempo)  # 0〜1
    odds = entry.expected_odds or 0.0

    # 期待値（超簡易）：勝率×オッズ（妙味はこれが一番伝わる）
    ev = win_prob * odds if odds > 0 else tempo

    return {
        "tempo": round(tempo, 2),
        "win_prob": round(win_prob * 100, 1),  # %
        "ev": round(ev, 2),
    }

def estimate_pace(entries: Iterable[HorseEntry]):
    entries = list(entries)
    n = len(entries) if entries else 1
    n_front = sum(1 for e in entries if e.run_style in ("NIGE", "SENKO"))
    ratio = n_front / n  # 逃げ先行の割合

    # 判定は今まで通り（説明しやすいので）
    if n_front >= 6:
        pace = "H"
        comment = "逃げ/先行が多くハイペース寄り"
    elif n_front >= 3:
        pace = "M"
        comment = "平均〜やや速めの想定"
    else:
        pace = "S"
        comment = "前に行く馬が少なくスロー寄り"

    return pace, comment, ratio

def convert_to_win_prob(tempo_score):
    # 仮ロジック：指数を0-1の範囲に収める
    prob = (tempo_score - 1.5) / 8
    prob = max(0.03, min(prob, 0.40))
    return round(prob * 100, 1)  # %

def convert_to_win_prob_from_tempo(tempo_score: float) -> float:
    """
    tempoを0〜1に変換（MVP用の疑似勝率）
    tempo だいたい 2.5〜5.5 を想定
    """
    x = (tempo_score - 2.5) / 3.0  # 2.5->0, 5.5->1
    x = max(0.05, min(0.60, 0.05 + 0.55 * x))  # 5%〜60%に収める
    return x

