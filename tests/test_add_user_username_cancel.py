"""Add-user username prompt must be cancellable from the inline card."""
from unittest.mock import AsyncMock


def _button_datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def _button_texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def test_add_entry_callback_has_cancel_button(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("vpn:add")

    run_async(bot_tt.add_entry_cb(update, context))

    kb = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
    assert "addcancel" in _button_datas(kb)
    assert "❌ Отмена" in _button_texts(kb)


def test_add_username_cancel_callback_stops_flow_and_opens_home_card(
    bot_tt, allowed_callback_update, context, run_async
):
    context.bot.delete_message = AsyncMock()
    update = allowed_callback_update("addcancel")
    update.callback_query.message.chat_id = 111111
    update.callback_query.message.message_id = 10
    context.user_data["pending_add_username"] = "bob"
    context.user_data["add_flow_scaffold"] = [(111111, 10), (111111, 11)]

    result = run_async(bot_tt.add_cancel_callback(update, context))

    assert result == bot_tt.ConversationHandler.END
    assert "pending_add_username" not in context.user_data
    update.callback_query.edit_message_text.assert_awaited_once()
    args = update.callback_query.edit_message_text.await_args.args
    kwargs = update.callback_query.edit_message_text.await_args.kwargs
    text = args[0]
    assert text == bot_tt.UI_WELCOME + "\n\n" + bot_tt.UI_HOME
    assert kwargs["parse_mode"] == bot_tt.ParseMode.HTML
    assert "nav:vpn" in _button_datas(kwargs["reply_markup"])
    assert "Создание пользователя отменено" not in text
    context.bot.delete_message.assert_awaited_once_with(chat_id=111111, message_id=11)
