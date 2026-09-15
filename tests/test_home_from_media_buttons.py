"""Home navigation must work from media/document messages."""
from unittest.mock import AsyncMock, MagicMock


def _datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_home_from_toml_document_sends_fresh_home_card(
    bot_tt, allowed_callback_update, context, run_async
):
    update = allowed_callback_update("nav:home")
    update.callback_query.message.chat_id = 111111
    update.callback_query.message.message_id = 44
    update.callback_query.message.document = object()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=99))
    context.bot.edit_message_reply_markup = AsyncMock()

    run_async(bot_tt.nav_callback(update, context))

    update.callback_query.edit_message_text.assert_not_awaited()
    context.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=111111,
        message_id=44,
        reply_markup=None,
    )
    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 111111
    assert kwargs["text"] == bot_tt.UI_WELCOME + "\n\n" + bot_tt.UI_HOME
    kb = kwargs["reply_markup"]
    assert {"nav:vpn", "nav:server"}.issubset(set(_datas(kb)))
    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 99
