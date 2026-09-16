"""list_usernames() raises ValueError on malformed TOML (tomlkit ParseError) —
correct for callers like user_detail_callback/nav:users that already wrap it
in try/except with a tailored "проверь credentials.toml" message. But
user_action_toml_callback/user_action_link_callback/user_action_all_callback/
user_search_text called it completely unguarded, so the same malformed file
fell through to the generic global "Внутренняя ошибка" instead."""
from unittest.mock import AsyncMock


def test_quick_toml_reports_corrupt_credentials(bot_tt, tt_paths, allowed_callback_update, context, run_async):
    tt_paths["CRED_FILE"].write_text("bad = ][", encoding="utf-8")
    update = allowed_callback_update("utc:alice")

    run_async(bot_tt.user_action_toml_callback(update, context))  # must not raise

    update.callback_query.answer.assert_awaited()


def test_quick_link_reports_corrupt_credentials(bot_tt, tt_paths, allowed_callback_update, context, run_async):
    tt_paths["CRED_FILE"].write_text("bad = ][", encoding="utf-8")
    update = allowed_callback_update("ulink:alice")

    run_async(bot_tt.user_action_link_callback(update, context))  # must not raise

    update.callback_query.answer.assert_awaited()


def test_quick_all_reports_corrupt_credentials(bot_tt, tt_paths, allowed_callback_update, context, run_async):
    tt_paths["CRED_FILE"].write_text("bad = ][", encoding="utf-8")
    update = allowed_callback_update("uall:alice")

    run_async(bot_tt.user_action_all_callback(update, context))  # must not raise

    update.callback_query.answer.assert_awaited()


def test_user_search_text_reports_corrupt_credentials(bot_tt, tt_paths, allowed_update, context, run_async):
    tt_paths["CRED_FILE"].write_text("bad = ][", encoding="utf-8")
    context.user_data["pending_user_search"] = True
    update = allowed_update("alice")
    update.message.reply_text = AsyncMock()

    run_async(bot_tt.user_search_text(update, context))  # must not raise

    update.message.reply_text.assert_awaited()
