"""Mirror of test_rotate_pick_burns_stale_prompt.py: rotate_pick_callback
(rotpick:) edits its message in place but never added it to
ROTATE_SCAFFOLD_KEY — so switching to another rotation afterwards via
user_action_rotate_callback (urot:) couldn't find it, and the rotpick:
prompt stayed hanging in the chat forever."""
from unittest.mock import AsyncMock, MagicMock


def test_urot_burns_previously_tracked_rotpick_prompt(
    bot_tt, allowed_callback_update, context, run_async
):
    pick_update = allowed_callback_update("rotpick:bob")
    pick_update.callback_query.edit_message_text = AsyncMock()
    run_async(bot_tt.rotate_pick_callback(pick_update, context))

    assert context.user_data.get(bot_tt.ROTATE_SCAFFOLD_KEY) == [
        (pick_update.callback_query.message.chat_id, pick_update.callback_query.message.message_id)
    ]

    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=100, chat_id=111111))
    context.bot.delete_message = AsyncMock()

    urot_update = allowed_callback_update("urot:alice")
    run_async(bot_tt.user_action_rotate_callback(urot_update, context))

    context.bot.delete_message.assert_any_call(
        chat_id=pick_update.callback_query.message.chat_id,
        message_id=pick_update.callback_query.message.message_id,
    )
