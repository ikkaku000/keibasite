from typing import Optional
from .models import HorseEntry


def avg_agari_rank(e: HorseEntry) -> Optional[float]:
    ranks = [e.last1_agari_rank, e.last2_agari_rank, e.last3_agari_rank]
    ranks = [r for r in ranks if r is not None and r > 0]
    if not ranks:
        return None
    return sum(ranks) / len(ranks)


def run_style_point(run_style: str, pace: str) -> float:
    if pace == "S":
        table = {"NIGE": 3.0, "SENKO": 2.0, "SASHI": 1.0, "OIKOMI": 0.5, "UNKNOWN": 1.0}
    elif pace == "H":
        table = {"NIGE": 1.0, "SENKO": 1.5, "SASHI": 2.5, "OIKOMI": 3.0, "UNKNOWN": 1.5}
    else:
        table = {"NIGE": 2.0, "SENKO": 2.0, "SASHI": 2.0, "OIKOMI": 2.0, "UNKNOWN": 2.0}
    return table.get(run_style, 1.5)


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


def calc_scores(entry: HorseEntry, pace: str) -> dict:
    a = avg_agari_rank(entry)
    tempo = run_style_point(entry.run_style, pace) + agari_point(a)
    ev = tempo * odds_bonus(entry.expected_odds)
    return {
        "tempo": round(tempo, 2),
        "ev": round(ev, 2),
    }

def estimate_pace(entries):
    n_front = sum(
        1 for e in entries
        if e.run_style in ("NIGE", "SENKO")
    )

    if n_front >= 6:
        return "H", "逃げ/先行が多くハイペース想定"
    elif n_front >= 3:
        return "M", "平均〜やや速め想定"
    else:
        return "S", "前が少なくスローペース想定"
    
def convert_to_win_prob(tempo_score):
    # 仮ロジック：指数を0-1の範囲に収める
    prob = (tempo_score - 1.5) / 8
    prob = max(0.03, min(prob, 0.40))
    return round(prob * 100, 1)  # %