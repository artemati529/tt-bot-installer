"""Unhandled errors go only to journalctl — the admin-chat notification was
removed: transient network errors dominated it, and even for real bugs the
generic "Внутренняя ошибка" card added noise without being actionable. The
full traceback is still in the logs for diagnosis."""

import logging

import telegram.error


def test_log_unhandled_error_logs_the_route_and_traceback(
    bot_tt, allowed_callback_update, context, run_async, caplog
):
    update = allowed_callback_update("nav:vpn")
    context.error = RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="tt-bot"):
        run_async(bot_tt.log_unhandled_error(update, context))

    assert "unhandled update error route=" in caplog.text
    assert "boom" in caplog.text


def test_log_unhandled_error_never_sends_a_chat_message(
    bot_tt, allowed_callback_update, context, run_async
):
    update = allowed_callback_update("nav:vpn")
    context.error = RuntimeError("boom")

    run_async(bot_tt.log_unhandled_error(update, context))

    context.bot.send_message.assert_not_called()


def test_log_unhandled_error_never_sends_a_chat_message_for_network_error(
    bot_tt, allowed_callback_update, context, run_async
):
    update = allowed_callback_update("nav:vpn")
    context.error = telegram.error.NetworkError("httpx.ReadError: boom")

    run_async(bot_tt.log_unhandled_error(update, context))

    context.bot.send_message.assert_not_called()
