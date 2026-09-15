"""«Меню» (и «🏠 Главная», и /cancel) должны сносить незакрытый prompt поиска.

Диалог добавления пользователя (vpn:add) прячет свой prompt "бесплатно" —
он рендерится через общий UI_MESSAGE_ID_KEY, и send_home_screen сносит его
через upsert_ui_message(force_new=True). Поиск (vpn:find) трекает свой
prompt отдельно, в USER_SEARCH_SCAFFOLD_KEY (_cleanup_user_search_scaffold),
и ни _go_home, ни ui_back_home, ни /cancel эту scaffold-очередь не чистили —
"🔍 Введи username для поиска" оставалось висеть в чате после тапа «Меню».
"""
from unittest.mock import AsyncMock


def test_go_home_deletes_leftover_search_prompt(bot_tt, context, allowed_update, run_async):
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.USER_SEARCH_SCAFFOLD_KEY] = [(111111, 99)]
    context.user_data["pending_user_search"] = True

    run_async(bot_tt._go_home(allowed_update(""), context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=99)
    assert bot_tt.USER_SEARCH_SCAFFOLD_KEY not in context.user_data


def test_ui_back_home_deletes_leftover_search_prompt_on_message_path(bot_tt, context, allowed_update, run_async):
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.USER_SEARCH_SCAFFOLD_KEY] = [(111111, 99)]
    context.user_data["pending_user_search"] = True

    run_async(bot_tt.ui_back_home(allowed_update(""), context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=99)
    assert bot_tt.USER_SEARCH_SCAFFOLD_KEY not in context.user_data


def test_ui_back_home_deletes_leftover_search_prompt_on_callback_path(bot_tt, context, allowed_callback_update, run_async):
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.USER_SEARCH_SCAFFOLD_KEY] = [(111111, 99)]
    context.user_data["pending_user_search"] = True

    run_async(bot_tt.ui_back_home(allowed_callback_update("nav:home"), context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=99)
    assert bot_tt.USER_SEARCH_SCAFFOLD_KEY not in context.user_data


def test_cancel_deletes_leftover_search_prompt(bot_tt, context, allowed_update, run_async):
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.USER_SEARCH_SCAFFOLD_KEY] = [(111111, 99)]
    context.user_data["pending_user_search"] = True

    run_async(bot_tt.cancel(allowed_update(""), context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=99)
    assert bot_tt.USER_SEARCH_SCAFFOLD_KEY not in context.user_data
