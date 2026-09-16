"""Два входа в ротацию пароля — быстрая кнопка на карточке пользователя (`urot:`,
трекает новый промпт в ROTATE_SCAFFOLD_KEY) и пикер в хабе VPN (`rotpick:`,
редактирует уже открытое сообщение на месте). `user_action_rotate_callback`
сжигает предыдущий промпт перед тем как показать новый — `rotate_pick_callback`
этого не делал: если начать ротацию через `urot:`, а потом переключиться на
другого пользователя через `rotpick:`, старый промпт от `urot:` оставался
висеть в чате и трекался как «живой», хотя реальная ротация уже шла для
другого username.
"""
from unittest.mock import AsyncMock, MagicMock


def test_rotate_pick_burns_previously_tracked_rotate_prompt(
    bot_tt, allowed_callback_update, context, run_async
):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=100, chat_id=111111))
    context.bot.delete_message = AsyncMock()

    urot_update = allowed_callback_update("urot:alice")
    run_async(bot_tt.user_action_rotate_callback(urot_update, context))
    assert context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY] == [(111111, 100)]

    pick_update = allowed_callback_update("rotpick:bob")
    pick_update.callback_query.edit_message_text = AsyncMock()
    run_async(bot_tt.rotate_pick_callback(pick_update, context))

    context.bot.delete_message.assert_any_call(chat_id=111111, message_id=100)
    # Старый urot:-промпт сожжён, а свой (rotpick:) теперь тоже трекается.
    assert context.user_data.get(bot_tt.ROTATE_SCAFFOLD_KEY) == [
        (pick_update.callback_query.message.chat_id, pick_update.callback_query.message.message_id)
    ]
