"""UI fallback must not leave duplicate active inline cards."""
from unittest.mock import AsyncMock, MagicMock


def test_upsert_ui_message_clears_old_keyboard_before_sending_fallback(bot_tt, context, run_async):
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 10
    context.bot.edit_message_text = AsyncMock(side_effect=bot_tt.BadRequest("message to edit not found"))
    context.bot.edit_message_reply_markup = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=20))

    run_async(
        bot_tt.upsert_ui_message(
            context,
            111111,
            "<b>Новая карточка</b>",
            parse_mode=bot_tt.ParseMode.HTML,
            reply_markup=bot_tt.hub_inline_kb(),
        )
    )

    context.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=111111,
        message_id=10,
        reply_markup=None,
    )
    context.bot.send_message.assert_awaited_once()
    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 20
