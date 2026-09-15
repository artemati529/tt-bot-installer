"""nav_callback не должен отвечать на callback-query, а затем делегировать в
ui_back_home/ui_open_vpn/ui_open_server, которые отвечают ЕЩЁ РАЗ — два
answerCallbackQuery на один тап меню. Telegram принимает только первый,
второй — лишний HTTP-запрос и лишняя строка в журнале."""
from unittest.mock import AsyncMock, MagicMock


def test_nav_home_answers_callback_query_exactly_once(bot_tt, allowed_callback_update, context, run_async):
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    update = allowed_callback_update("nav:home")

    run_async(bot_tt.nav_callback(update, context))

    assert update.callback_query.answer.await_count == 1


def test_nav_vpn_answers_callback_query_exactly_once(bot_tt, allowed_callback_update, context, run_async):
    context.bot.edit_message_text = AsyncMock()
    update = allowed_callback_update("nav:vpn")

    run_async(bot_tt.nav_callback(update, context))

    assert update.callback_query.answer.await_count == 1


def test_nav_server_answers_callback_query_exactly_once(bot_tt, allowed_callback_update, context, run_async):
    context.bot.edit_message_text = AsyncMock()
    update = allowed_callback_update("nav:server")

    run_async(bot_tt.nav_callback(update, context))

    assert update.callback_query.answer.await_count == 1


def test_nav_home_still_shows_menu_toast(bot_tt, allowed_callback_update, context, run_async):
    context.bot.edit_message_text = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    update = allowed_callback_update("nav:home")

    run_async(bot_tt.nav_callback(update, context))

    update.callback_query.answer.assert_awaited_once_with(text="Меню", show_alert=False)
