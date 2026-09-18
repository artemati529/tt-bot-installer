"""nav:logs and nav:cert had no try/except unlike the sibling nav:users:
branch — a rare exception (e.g. journalctl unavailable, cert file parse
error) propagated uncaught to the global error handler, leaving the card
frozen with no feedback beyond journalctl (worse now that unhandled
errors don't reach the chat at all, see log_unhandled_error)."""


def test_nav_logs_shows_error_card_on_failure(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("journalctl unavailable")

    monkeypatch.setattr(bot_tt, "build_logs_view", boom)
    update = allowed_callback_update("nav:logs")

    run_async(bot_tt.nav_callback(update, context))  # must not raise

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Не удалось показать" in text


def test_nav_cert_shows_error_card_on_failure(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("cert parse failed")

    monkeypatch.setattr(bot_tt, "get_cert_card_data", boom)
    update = allowed_callback_update("nav:cert")

    run_async(bot_tt.nav_callback(update, context))  # must not raise

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Не удалось показать" in text
