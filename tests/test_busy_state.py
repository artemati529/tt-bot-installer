from unittest.mock import AsyncMock


def test_busy_guard_rejects_callback_without_calling_handler(bot_tt, allowed_callback_update, context, run_async):
    calls = []

    async def handler(update, ctx):
        calls.append((update, ctx))

    bot_tt.busy_set("обновление ОС")
    try:
        update = allowed_callback_update("nav:home")
        run_async(bot_tt.busy_guard(handler)(update, context))
    finally:
        bot_tt.busy_clear()

    assert calls == []
    update.callback_query.answer.assert_awaited_once()
    assert "Жди: обновление ОС" in update.callback_query.answer.await_args.kwargs["text"]


def test_busy_guard_allows_handler_when_idle(bot_tt, allowed_callback_update, context, run_async):
    calls = []

    async def handler(update, ctx):
        calls.append((update, ctx))

    bot_tt.busy_clear()
    update = allowed_callback_update("nav:home")
    run_async(bot_tt.busy_guard(handler)(update, context))

    assert calls == [(update, context)]
    assert update.callback_query.answer.await_count == 0


def test_status_reports_busy_operation(bot_tt, allowed_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_services_status_line", lambda: "trusttunnel: active · tt-bot: active")
    update = allowed_update("/status")
    update.message.reply_text = AsyncMock()

    bot_tt.busy_set("обновление сертификата")
    try:
        run_async(bot_tt.status(update, context))
    finally:
        bot_tt.busy_clear()

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "tt-bot жив" in text
    assert "обновление сертификата" in text
    assert "trusttunnel: active" in text
