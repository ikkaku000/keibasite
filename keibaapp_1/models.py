from django.db import models


class Race(models.Model):
    GRADE_CHOICES = [("G1", "G1"), ("G2", "G2"), ("G3", "G3")]

    name = models.CharField(max_length=100)
    race_date = models.DateField()
    course = models.CharField(max_length=100)  # 例：東京 ダ1600
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES)
    track_condition = models.CharField(max_length=10, blank=True, default="")  # 良/稍/重/不

    pace = models.CharField(max_length=1, blank=True, default="")  # S/M/H
    pace_comment = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race_date} {self.name} ({self.grade})"


class HorseEntry(models.Model):
    RUN_STYLE_CHOICES = [
        ("NIGE", "逃げ"),
        ("SENKO", "先行"),
        ("KOUI", "好位"),
        ("SASHI", "差し"),
        ("OIKOMI", "追込"),
        ("UNKNOWN", "不明"),
    ]

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="entries")
    horse_name = models.CharField(max_length=100)
    gate = models.PositiveIntegerField(default=0)
    number = models.PositiveIntegerField(default=0)
    jockey = models.CharField(max_length=100, blank=True, default="")
    run_style = models.CharField(max_length=10, choices=RUN_STYLE_CHOICES, default="UNKNOWN")

    last1_agari_rank = models.PositiveIntegerField(null=True, blank=True)
    last2_agari_rank = models.PositiveIntegerField(null=True, blank=True)
    last3_agari_rank = models.PositiveIntegerField(null=True, blank=True)

    last1_agari_3f = models.FloatField(null=True, blank=True)
    last2_agari_3f = models.FloatField(null=True, blank=True)
    last3_agari_3f = models.FloatField(null=True, blank=True)

    last1_field_size = models.PositiveIntegerField(null=True, blank=True)
    last2_field_size = models.PositiveIntegerField(null=True, blank=True)
    last3_field_size = models.PositiveIntegerField(null=True, blank=True)

    last1_corner4_pos = models.PositiveIntegerField(null=True, blank=True)
    last2_corner4_pos = models.PositiveIntegerField(null=True, blank=True)
    last3_corner4_pos = models.PositiveIntegerField(null=True, blank=True)

    expected_odds = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race.name} - {self.horse_name}"


class RaceAnalysisSnapshot(models.Model):
    PACE_CHOICES = [
        ("S", "スロー"),
        ("M", "ミドル"),
        ("H", "ハイ"),
    ]

    race = models.ForeignKey(
        Race,
        on_delete=models.CASCADE,
        related_name="analysis_snapshots"
    )

    predicted_pace = models.CharField(max_length=1, choices=PACE_CHOICES)
    pace_comment = models.CharField(max_length=255, blank=True, default="")
    front_ratio = models.FloatField(default=0.0)

    n_nige = models.IntegerField(default=0)
    n_front = models.IntegerField(default=0)
    pace_pressure = models.FloatField(default=0.0)

    field_agari_avg = models.FloatField(null=True, blank=True)

    model_version = models.CharField(max_length=30, blank=True, default="v1")
    calculated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race.name} / {self.predicted_pace} / {self.calculated_at:%Y-%m-%d %H:%M}"


class EntryAnalysisSnapshot(models.Model):
    RUN_STYLE_CHOICES = [
        ("NIGE", "逃げ"),
        ("SENKO", "先行"),
        ("KOUI", "好位"),
        ("SASHI", "差し"),
        ("OIKOMI", "追込"),
        ("UNKNOWN", "不明"),
    ]

    race_snapshot = models.ForeignKey(
        RaceAnalysisSnapshot,
        on_delete=models.CASCADE,
        related_name="entry_snapshots"
    )

    horse_entry = models.ForeignKey(
        HorseEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analysis_snapshots"
    )

    horse_name = models.CharField(max_length=100)
    horse_number = models.PositiveIntegerField(null=True, blank=True)
    gate = models.PositiveIntegerField(null=True, blank=True)
    jockey = models.CharField(max_length=100, blank=True, default="")

    run_style = models.CharField(max_length=10, choices=RUN_STYLE_CHOICES, default="UNKNOWN")
    corner4_index = models.FloatField(null=True, blank=True)
    agari_avg_rank = models.FloatField(null=True, blank=True)

    tempo_raw = models.FloatField(default=0.0)
    tempo = models.FloatField(default=0.0)
    pseudo_win_prob = models.FloatField(default=0.0)
    value_index = models.FloatField(null=True, blank=True)

    expected_odds = models.FloatField(null=True, blank=True)

    rank_by_prob = models.PositiveIntegerField(null=True, blank=True)
    rank_by_value = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race_snapshot.race.name} - {self.horse_name}"


class EntryResultSnapshot(models.Model):
    entry_snapshot = models.OneToOneField(
        EntryAnalysisSnapshot,
        on_delete=models.CASCADE,
        related_name="result_snapshot"
    )

    finish_position = models.PositiveIntegerField(null=True, blank=True)
    corner4_actual = models.PositiveIntegerField(null=True, blank=True)
    agari_actual_rank = models.PositiveIntegerField(null=True, blank=True)

    win_payoff = models.PositiveIntegerField(null=True, blank=True)
    place_payoff = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"結果: {self.entry_snapshot.horse_name}"


class RaceResultSnapshot(models.Model):
    race_snapshot = models.OneToOneField(
        RaceAnalysisSnapshot,
        on_delete=models.CASCADE,
        related_name="race_result"
    )

    bet_amount = models.PositiveIntegerField(null=True, blank=True, help_text="そのレースでの合計投資額")
    return_amount = models.PositiveIntegerField(null=True, blank=True, help_text="そのレースでの合計払戻額")

    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race_snapshot.race.name} 回収結果"