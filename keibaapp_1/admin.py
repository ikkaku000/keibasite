import csv
import io
from django import forms
from django.contrib import admin, messages
from .models import Race, HorseEntry


# --- CSV貼り付け用のフォーム（DBには保存しない入力欄） ---
class RaceAdminForm(forms.ModelForm):
    csv_input = forms.CharField(
        required=False,
        label="CSV貼り付け（HorseEntry一括登録/更新）",
        widget=forms.Textarea(attrs={
            "rows": 10,
            "style": "font-family: ui-monospace, SFMono-Regular, Menlo, monospace; width: 100%;",
            "placeholder": (
                "例）\n"
                "number,gate,horse_name,jockey,run_style,expected_odds,last1,last2,last3\n"
                "1,1,サンプルA,武豊,SENKO,5.2,3,2,4\n"
                "2,1,サンプルB,川田,SASHI,8.5,2,6,5\n"
                "\n"
                "run_style は NIGE/SENKO/SASHI/OIKOMI/UNKNOWN（逃げ/先行/差し/追込 もOK）"
            )
        }),
        help_text="貼り付けて保存すると、同じ馬番(number)は更新、なければ新規作成します。空なら何もしません。",
    )

    class Meta:
        model = Race
        fields = "__all__"


def _to_int(v):
    v = (v or "").strip()
    return int(v) if v else None


def _to_float(v):
    v = (v or "").strip()
    return float(v) if v else None


def _normalize_run_style(v: str) -> str:
    v = (v or "").strip().upper()
    jp_map = {
        "逃げ": "NIGE",
        "先行": "SENKO",
        "差し": "SASHI",
        "追込": "OIKOMI",
        "追い込み": "OIKOMI",
        "不明": "UNKNOWN",
    }
    if v in jp_map:
        return jp_map[v]
    if v in {"NIGE", "SENKO", "SASHI", "OIKOMI", "UNKNOWN"}:
        return v
    return "UNKNOWN"


def parse_and_upsert_entries(race: Race, csv_text: str) -> tuple[int, int]:
    """
    returns: (created_count, updated_count)

    対応カラム:
      number, gate, horse_name, jockey, run_style, expected_odds,
      last1, last2, last3,
      last1_fs, last1_c4, last2_fs, last2_c4, last3_fs, last3_c4
    """
    text = (csv_text or "").strip()
    if not text:
        return (0, 0)

    text = text.replace("\u3000", " ")

    f = io.StringIO(text)
    sample = f.read(2048)
    f.seek(0)

    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    has_header = "number" in first_line.lower()

    created = 0
    updated = 0

    if has_header:
        reader = csv.DictReader(f)
        for row in reader:
            number = _to_int(row.get("number"))
            if not number:
                continue

            defaults = {
                "gate": _to_int(row.get("gate")) or 0,
                "horse_name": (row.get("horse_name") or "").strip(),
                "jockey": (row.get("jockey") or "").strip(),
                "run_style": _normalize_run_style(row.get("run_style") or ""),
                "expected_odds": _to_float(row.get("expected_odds")),

                "last1_agari_rank": _to_int(row.get("last1")),
                "last2_agari_rank": _to_int(row.get("last2")),
                "last3_agari_rank": _to_int(row.get("last3")),

                "last1_field_size": _to_int(row.get("last1_fs")),
                "last1_corner4_pos": _to_int(row.get("last1_c4")),
                "last2_field_size": _to_int(row.get("last2_fs")),
                "last2_corner4_pos": _to_int(row.get("last2_c4")),
                "last3_field_size": _to_int(row.get("last3_fs")),
                "last3_corner4_pos": _to_int(row.get("last3_c4")),
            }

            obj, is_created = HorseEntry.objects.update_or_create(
                race=race,
                number=number,
                defaults=defaults
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1

    else:
        # ヘッダーなし:
        # number, gate, horse_name, jockey, run_style, expected_odds,
        # last1, last2, last3, last1_fs, last1_c4, last2_fs, last2_c4, last3_fs, last3_c4
        reader = csv.reader(f)
        for cols in reader:
            if not cols or all((c or "").strip() == "" for c in cols):
                continue
            if len(cols) < 5:
                continue

            number = _to_int(cols[0])
            if not number:
                continue

            defaults = {
                "gate": _to_int(cols[1]) or 0 if len(cols) > 1 else 0,
                "horse_name": (cols[2] or "").strip() if len(cols) > 2 else "",
                "jockey": (cols[3] or "").strip() if len(cols) > 3 else "",
                "run_style": _normalize_run_style(cols[4] if len(cols) > 4 else ""),
                "expected_odds": _to_float(cols[5]) if len(cols) > 5 else None,

                "last1_agari_rank": _to_int(cols[6]) if len(cols) > 6 else None,
                "last2_agari_rank": _to_int(cols[7]) if len(cols) > 7 else None,
                "last3_agari_rank": _to_int(cols[8]) if len(cols) > 8 else None,

                "last1_field_size": _to_int(cols[9]) if len(cols) > 9 else None,
                "last1_corner4_pos": _to_int(cols[10]) if len(cols) > 10 else None,
                "last2_field_size": _to_int(cols[11]) if len(cols) > 11 else None,
                "last2_corner4_pos": _to_int(cols[12]) if len(cols) > 12 else None,
                "last3_field_size": _to_int(cols[13]) if len(cols) > 13 else None,
                "last3_corner4_pos": _to_int(cols[14]) if len(cols) > 14 else None,
            }

            obj, is_created = HorseEntry.objects.update_or_create(
                race=race,
                number=number,
                defaults=defaults
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1

    return (created, updated)


class HorseEntryInline(admin.TabularInline):
    model = HorseEntry
    extra = 18
    fields = (
    "number", "gate", "horse_name", "jockey",
    "run_style", "expected_odds",
    "last1_agari_rank", "last2_agari_rank", "last3_agari_rank",
    "last1_field_size", "last1_corner4_pos",
    "last2_field_size", "last2_corner4_pos",
    "last3_field_size", "last3_corner4_pos",
    )
    ordering = ("number",)


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    form = RaceAdminForm
    list_display = ("race_date", "name", "grade", "course", "track_condition", "pace")
    list_filter = ("grade", "race_date")
    search_fields = ("name", "course")
    inlines = [HorseEntryInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        csv_text = form.cleaned_data.get("csv_input")
        if csv_text and csv_text.strip():
            try:
                created, updated = parse_and_upsert_entries(obj, csv_text)
                messages.success(
                    request,
                    f"CSV取込完了：新規 {created} 件 / 更新 {updated} 件"
                )
            except Exception as e:
                messages.error(request, f"CSV取込に失敗しました：{e}")


@admin.register(HorseEntry)
class HorseEntryAdmin(admin.ModelAdmin):
    list_display = ("race", "number", "horse_name", "run_style", "expected_odds")
    list_filter = ("race", "run_style")
    search_fields = ("horse_name", "jockey")