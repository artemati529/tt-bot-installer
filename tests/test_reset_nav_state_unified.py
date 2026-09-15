"""Единая reset_nav_state(context) — сброс состояния при уходе с экрана
(nav_callback, ui_back_home, _go_home, cancel) в одном месте: чистит scaffold
поиска и ротации одинаково для всех nav:-маршрутов, не только nav:home/vpn/server."""
from unittest.mock import AsyncMock, MagicMock


def test_nav_close_burns_pending_search_prompt(bot_tt, allowed_callback_update, context, run_async):
    """Раньше это работало только для nav:home — теперь для любого nav:."""
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.USER_SEARCH_SCAFFOLD_KEY] = [(111111, 99)]
    context.user_data["pending_user_search"] = True

    update = allowed_callback_update("nav:close")
    update.callback_query.message.delete = AsyncMock()

    run_async(bot_tt.nav_callback(update, context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=99)
    assert context.user_data.get(bot_tt.USER_SEARCH_SCAFFOLD_KEY) in (None, [])


def test_nav_close_burns_pending_rotate_prompt(bot_tt, allowed_callback_update, context, run_async):
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY] = [(111111, 100)]

    update = allowed_callback_update("nav:close")
    update.callback_query.message.delete = AsyncMock()

    run_async(bot_tt.nav_callback(update, context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=100)


def test_ui_back_home_also_burns_rotate_prompt_when_called_directly(bot_tt, allowed_update, context, run_async):
    """ui_back_home раньше не звал _cleanup_rotate_scaffold сам — это
    маскировалось тем, что единственный вызывающий (nav_callback) уже
    сжигал ротацию до делегирования. reset_nav_state делает это в одном
    месте, так что ui_back_home корректен и при прямом вызове (message-путь
    /start -> _go_home тоже использует reset_nav_state, но здесь проверяем
    именно ui_back_home)."""
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY] = [(111111, 100)]

    update = allowed_update("")
    run_async(bot_tt.ui_back_home(update, context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=100)


def test_cancel_still_pops_pending_tt_update(bot_tt, allowed_update, context, run_async):
    context.user_data["pending_tt_update"] = {"current": "1.0", "latest": "2.0"}
    update = allowed_update("")
    update.message.reply_text = AsyncMock()

    result = run_async(bot_tt.cancel(update, context))

    assert result == bot_tt.ConversationHandler.END
    assert "pending_tt_update" not in context.user_data
