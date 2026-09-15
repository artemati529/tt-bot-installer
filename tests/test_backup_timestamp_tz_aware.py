"""_backup_timestamp() был datetime.now() без tz (DTZ005) — не баг (штамп имени
файла, никогда не сравнивается с другим временем), но .astimezone() убирает
находку без изменения отображаемых цифр (локальное время как было)."""
import re


def test_backup_timestamp_format_unchanged(bot_tt):
    stamp = bot_tt._backup_timestamp()
    assert re.fullmatch(r"\d{8}-\d{6}", stamp), stamp


def test_backup_timestamp_matches_local_wall_clock(bot_tt, monkeypatch):
    import datetime as dt

    fixed = dt.datetime(2026, 3, 5, 14, 30, 7)  # noqa: DTZ001 — имитирует naive datetime.now()

    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(bot_tt.dt, "datetime", FixedDatetime)
    assert bot_tt._backup_timestamp() == "20260305-143007"
