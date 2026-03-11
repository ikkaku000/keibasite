import csv
import io
from django import forms
from django.contrib import admin, messages
from .models import Race, HorseEntry, RaceAnalysisSnapshot, EntryAnalysisSnapshot, EntryResultSnapshot


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
                "horse_name,gate,number,jockey,expected_odds,last1_corner4_pos,last2_corner4_pos,last3_corner4_pos,last1_agari_3f,last2_agari_3f,last3_agari_3f\n"
                "サンプルA,1,1,武豊,5.2,2,3,4,35.1,35.4,35.8\n"
                "サンプルB,1,2,川田,8.5,6,5,7,34.9,35.6,36.0\n"
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
        "好位": "KOUI",
        "差し": "SASHI",
        "追込": "OIKOMI",
        "追い込み": "OIKOMI",
        "不明": "UNKNOWN",
    }
    if v in jp_map:
        return jp_map[v]
    if v in {"NIGE", "SENKO", "KOUI", "SASHI", "OIKOMI", "UNKNOWN"}:
        return v
    return "UNKNOWN"


def parse_and_upsert_entries(race: Race, csv_text: str) -> tuple[int, int]:
    """
    returns: (created_count, updated_count)

    対応カラム（最新）:
      horse_name, gate, number, jockey, expected_odds,
      last1_corner4_pos, last2_corner4_pos, last3_corner4_pos,
      last1_agari_3f, last2_agari_3f, last3_agari_3f

    旧カラムも一部互換対応:
      run_style, last1, last2, last3,
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
    lower_first = first_line.lower()
    has_header = ("number" in lower_first) or ("horse_name" in lower_first)

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

                    # 旧: 上がり順位
                    "last1_agari_rank": _to_int(row.get("last1")),
                    "last2_agari_rank": _to_int(row.get("last2")),
                    "last3_agari_rank": _to_int(row.get("last3")),

                    # 新: 上がり3F
                    "last1_agari_3f": _to_float(row.get("last1_agari_3f")),
                    "last2_agari_3f": _to_float(row.get("last2_agari_3f")),
                    "last3_agari_3f": _to_float(row.get("last3_agari_3f")),

                    # 頭数（新旧両対応）
                    "last1_field_size": _to_int(row.get("last1_field_size") or row.get("last1_fs")),
                    "last2_field_size": _to_int(row.get("last2_field_size") or row.get("last2_fs")),
                    "last3_field_size": _to_int(row.get("last3_field_size") or row.get("last3_fs")),

                    # 4角位置（新旧両対応）
                    "last1_corner4_pos": _to_int(row.get("last1_corner4_pos") or row.get("last1_c4")),
                    "last2_corner4_pos": _to_int(row.get("last2_corner4_pos") or row.get("last2_c4")),
                    "last3_corner4_pos": _to_int(row.get("last3_corner4_pos") or row.get("last3_c4")),
                    }

            obj, is_created = HorseEntry.objects.update_or_create(
                race=race,
                number=number,
                defaults=defaults
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1

    else:
        # ヘッダーなしは旧仕様のまま簡易対応
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
        "last1_agari_3f", "last2_agari_3f", "last3_agari_3f",
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


@admin.register(RaceAnalysisSnapshot)
class RaceAnalysisSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "race",
        "predicted_pace",
        "front_ratio",
        "model_version",
        "calculated_at",
    )
    list_filter = ("predicted_pace", "model_version")
    search_fields = ("race__name",)


@admin.register(EntryAnalysisSnapshot)
class EntryAnalysisSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "race_snapshot",
        "horse_name",
        "run_style",
        "pseudo_win_prob",
        "value_index",
        "rank_by_prob",
        "rank_by_value",
    )
    list_filter = ("run_style",)
    search_fields = ("horse_name",)


@admin.register(EntryResultSnapshot)
class EntryResultSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "entry_snapshot",
        "finish_position",
        "win_payoff",
        "place_payoff",
        "created_at",
    )