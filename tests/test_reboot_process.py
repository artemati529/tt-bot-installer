"""Reboot action must not leave an unmanaged child process."""
from unittest.mock import AsyncMock


def test_reboot_callback_uses_managed_reboot_helper(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    calls = []

    def fake_reboot():
        calls.append("reboot")

    def fail_popen(*args, **kwargs):
        raise AssertionError("reboot_callback must not call subprocess.Popen directly")

    monkeypatch.setattr(bot_tt, "_request_system_reboot_sync", fake_reboot, raising=False)
    monkeypatch.setattr(bot_tt.subprocess, "Popen", fail_popen)
    context.bot.send_message = AsyncMock()
    update = allowed_callback_update("rbdo")

    run_async(bot_tt.reboot_callback(update, context))

    assert calls == ["reboot"]
    context.bot.send_message.assert_awaited_once()


def test_reboot_callback_rejects_reboot_while_busy(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    calls = []
    monkeypatch.setattr(bot_tt, "_request_system_reboot_sync", lambda: calls.append("reboot"), raising=False)
    context.bot.send_message = AsyncMock()
    update = allowed_callback_update("rbdo")

    bot_tt.busy_set("обновление ОС")
    try:
        run_async(bot_tt.reboot_callback(update, context))
    finally:
        bot_tt.busy_clear()

    assert calls == []
    context.bot.send_message.assert_not_awaited()
    assert update.callback_query.answer.await_count >= 1
    assert "Жди" in (update.callback_query.answer.await_args.kwargs.get("text") or "")


def test_reboot_cancel_still_works_while_busy(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("rbcancel")

    bot_tt.busy_set("обновление ОС")
    try:
        run_async(bot_tt.reboot_callback(update, context))
    finally:
        bot_tt.busy_clear()

    update.callback_query.edit_message_text.assert_awaited_once()
    assert "отменена" in update.callback_query.edit_message_text.await_args.args[0]
