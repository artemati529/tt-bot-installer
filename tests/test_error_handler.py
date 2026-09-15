"""Unhandled errors must be visible in Telegram, not only journalctl."""

from unittest.mock import AsyncMock


def test_log_unhandled_error_notifies_admin_chat(
    bot_tt, allowed_callback_update, context, run_async
):
    update = allowed_callback_update("nav:vpn")
    context.error = RuntimeError("boom")
    context.bot.send_message = AsyncMock()

    run_async(bot_tt.log_unhandled_error(update, context))

    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 111111
    assert "Внутренняя ошибка" in kwargs["text"]
    assert "journalctl -u tt-bot" in kwargs["text"]
