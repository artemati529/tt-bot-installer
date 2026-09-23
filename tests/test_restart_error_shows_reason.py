"""При сбое ручного рестарта админ видел только «Не удалось перезапустить
сервис», причина (например, битый vpn.toml) уходила лишь в журнал — в
отличие от delete/rotate/restore, которые показывают текст CommandError."""
from unittest.mock import AsyncMock


def _run(bot_tt, exc, allowed_callback_update, context, run_async, monkeypatch):
    def boom(**kw):
        raise exc

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", boom)
    update = allowed_callback_update("ttrst_yes")
    update.callback_query.edit_message_text = AsyncMock()
    run_async(bot_tt.restart_tt_confirm_callback(update, context))
    bot_tt.busy_clear()
    return update.callback_query.edit_message_text.await_args.args[0]


def test_command_error_reason_is_shown(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    text = _run(bot_tt, bot_tt.CommandError("Проверка конфигов не прошла: vpn.toml: некорректный TOML"),
                allowed_callback_update, context, run_async, monkeypatch)
    assert "vpn.toml: некорректный TOML" in text


def test_unexpected_error_stays_generic(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    text = _run(bot_tt, RuntimeError("internal <detail>"), allowed_callback_update, context, run_async, monkeypatch)
    assert "Не удалось перезапустить" in text
    assert "internal" not in text
