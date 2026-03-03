from django.db import models


class Race(models.Model):
    GRADE_CHOICES = [("G1", "G1"), ("G2", "G2"), ("G3", "G3")]

    name = models.CharField(max_length=100)
    race_date = models.DateField()
    course = models.CharField(max_length=100)  # 例：東京 ダ1600
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES)
    track_condition = models.CharField(max_length=10, blank=True, default="")  # 良/稍/重/不

    # MVP用：想定ペースは手入力でOK（後で自動化できる）
    pace = models.CharField(max_length=1, blank=True, default="")  # S/M/H
    pace_comment = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race_date} {self.name} ({self.grade})"


class HorseEntry(models.Model):
    RUN_STYLE_CHOICES = [
        ("NIGE", "逃げ"),
        ("SENKO", "先行"),
        ("SASHI", "差し"),
        ("OIKOMI", "追込"),
        ("UNKNOWN", "不明"),
    ]

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="entries")
    horse_name = models.CharField(max_length=100)
    gate = models.PositiveIntegerField(default=0)    # 枠
    number = models.PositiveIntegerField(default=0)  # 馬番
    jockey = models.CharField(max_length=100, blank=True, default="")
    run_style = models.CharField(max_length=10, choices=RUN_STYLE_CHOICES, default="UNKNOWN")

    # MVP：過去3走の上がり順位（入力できればOK、なければ空）
    last1_agari_rank = models.PositiveIntegerField(null=True, blank=True)
    last2_agari_rank = models.PositiveIntegerField(null=True, blank=True)
    last3_agari_rank = models.PositiveIntegerField(null=True, blank=True)

    expected_odds = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.race.name} - {self.horse_name}"