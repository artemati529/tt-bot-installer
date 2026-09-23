"""Парсинг certbot.timer: (last, next) срабатываний.

`systemctl show` разбирается по Key=Value, а не по строкам: с --value число
строк в выводе не совпадает с числом -p (TriggerUSecReal — не настоящее
свойство systemd, пустые значения тоже пропускаются), ActiveState смещается
в позиции, и карточка показывала "(timer n/a)" у вполне живого таймера.
"""
import datetime as dt

LIST_TIMERS_LINE = (
    "Tue 2026-09-15 07:54:01 CEST 3h 54min "
    "Mon 2026-09-14 14:34:30 CEST certbot.timer certbot.service"
)

# Реальный сервер (новый systemd): человекочитаемые таймстампы.
# ВАЖНО: ровно три строки — строки на несуществующее свойство нет,
# ActiveState стоит ТРЕТЬЕЙ, а не четвёртой (старый код читал vals[3]).
SHOW_OUTPUT_ACTIVE = (
    "LastTriggerUSec=Mon 2026-09-14 14:34:30 CEST\n"
    "NextElapseUSecRealtime=Tue 2026-09-15 07:54:01 CEST\n"
    "ActiveState=active"
)

# Старый systemd: *USec-свойства отдаёт сырыми usec.
LAST_USEC = int(dt.datetime(2026, 9, 14, 14, 34, 30, tzinfo=dt.timezone.utc).timestamp() * 1_000_000)
NEXT_USEC = int(dt.datetime(2026, 9, 15, 7, 54, 1, tzinfo=dt.timezone.utc).timestamp() * 1_000_000)
SHOW_OUTPUT_USEC = (
    f"LastTriggerUSec={LAST_USEC}\n"
    f"NextElapseUSecRealtime={NEXT_USEC}\n"
    "ActiveState=active"
)


def _patch(
    bot_tt,
    monkeypatch,
    show_out: str | None = None,
    run_shell_code: int = 0,
):
    if show_out is None:
        show_out = SHOW_OUTPUT_ACTIVE

    def fake_run_argv(cmd, timeout=None, **kwargs):
        if cmd[:3] == ["systemctl", "show", "certbot.timer"]:
            return run_shell_code, show_out, ""
        return 0, "", ""

    def fake_run_cmd(cmd, timeout=None, **kwargs):
        if "list-timers" in " ".join(cmd):
            return LIST_TIMERS_LINE
        if cmd[:2] == ["systemctl", "is-active"]:
            return "active"
        return ""

    monkeypatch.setattr(bot_tt, "run_argv", fake_run_argv)
    monkeypatch.setattr(bot_tt, "run_cmd", fake_run_cmd)


def test_next_trigger_shows_time_left(bot_tt, monkeypatch):
    _patch(bot_tt, monkeypatch)

    _, next_trigger = bot_tt._certbot_timer_lines()

    assert "3h 54min" in next_trigger
    assert "UTC left" not in next_trigger
    assert "(timer n/a)" not in next_trigger


def test_active_timer_on_third_line_not_reported_na(bot_tt, monkeypatch):
    """Баг с реального сервера: ActiveState третьей строкой (строки на
    несуществующее свойство нет) раньше читался как «n/a»."""
    _patch(bot_tt, monkeypatch)

    last, next_trigger = bot_tt._certbot_timer_lines()

    assert "Mon 2026-09-14 14:34:30" in last
    assert "Tue 2026-09-15 07:54:01" in next_trigger
    assert "timer n/a" not in next_trigger


def test_raw_usec_normalized_to_human(bot_tt, monkeypatch):
    _patch(bot_tt, monkeypatch, show_out=SHOW_OUTPUT_USEC)

    last, next_trigger = bot_tt._certbot_timer_lines()

    assert str(LAST_USEC) not in last
    assert "2026-09-14 14:34 UTC" in last
    assert "3h 54min" in next_trigger


def test_never_triggered_no_positional_shift(bot_tt, monkeypatch):
    """LastTriggerUSec пустой — с Key=Value позиций не съезжает,
    ActiveState читается по имени."""
    show_out = "LastTriggerUSec=\n" + SHOW_OUTPUT_ACTIVE.splitlines()[1] + "\nActiveState=active"
    _patch(bot_tt, monkeypatch, show_out=show_out)

    last, next_trigger = bot_tt._certbot_timer_lines()

    assert last == "ещё не запускался"
    assert "timer n/a" not in next_trigger


def test_unit_missing(bot_tt, monkeypatch):
    _patch(bot_tt, monkeypatch, show_out="", run_shell_code=4)

    last, next_trigger = bot_tt._certbot_timer_lines()

    assert last == "n/a"
    assert "timer не найден" in next_trigger
    assert "timer n/a" not in next_trigger


def test_timer_inactive_flagged(bot_tt, monkeypatch):
    show_out = (
        "LastTriggerUSec=Mon 2026-09-08 03:12:00 CEST\n"
        "NextElapseUSecRealtime=\n"
        "ActiveState=inactive"
    )
    monkeypatch.setattr(
        bot_tt, "run_argv", lambda c, timeout=None, **kw: (0, show_out, "")
    )

    def fake_run_cmd(cmd, timeout=None, **kwargs):
        # Инактивный таймер в list-timers не фигурирует.
        if cmd[:2] == ["systemctl", "is-active"]:
            return "active"
        return ""

    monkeypatch.setattr(bot_tt, "run_cmd", fake_run_cmd)

    _, next_trigger = bot_tt._certbot_timer_lines()

    assert "timer inactive" in next_trigger
    assert "timer n/a" not in next_trigger


def test_list_timers_runs_with_c_locale(bot_tt, monkeypatch):
    seen = []
    monkeypatch.setattr(
        bot_tt, "run_argv", lambda c, timeout=None, **kw: (0, SHOW_OUTPUT_ACTIVE, "")
    )

    def fake_run_cmd(cmd, timeout=None, **kwargs):
        seen.append(cmd)
        if "list-timers" in " ".join(cmd):
            return LIST_TIMERS_LINE
        return "active"

    monkeypatch.setattr(bot_tt, "run_cmd", fake_run_cmd)
    bot_tt._certbot_timer_lines()

    lt = [c for c in seen if "list-timers" in " ".join(c)]
    assert lt, "list-timers call not found"
    # Локаль зафиксирована: LEFT колонка не переключится на «осталось 6 ч».
    assert any("LC_ALL=C" in part for c in lt for part in c)
