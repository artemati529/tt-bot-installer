"""Fast user-card actions and list-based actions should stay aligned."""


def _button_datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_rotate_entrypoints_use_same_prompt_text(
    bot_tt, allowed_callback_update, context, run_async
):
    list_update = allowed_callback_update("rotpick:alice")

    run_async(bot_tt.rotate_pick_callback(list_update, context))

    list_text = list_update.callback_query.edit_message_text.await_args.args[0]
    assert context.user_data["pending_rotate_username"] == "alice"

    context.user_data.clear()
    context.bot.send_message.reset_mock()
    quick_update = allowed_callback_update("urot:alice")

    run_async(bot_tt.user_action_rotate_callback(quick_update, context))

    quick_text = context.bot.send_message.await_args.kwargs["text"]
    assert context.user_data["pending_rotate_username"] == "alice"
    assert list_text == quick_text


def test_delete_entrypoints_use_same_confirm_card(
    bot_tt, allowed_callback_update, context, run_async
):
    list_update = allowed_callback_update("delask:alice")
    quick_update = allowed_callback_update("udel:alice")

    run_async(bot_tt.delete_user_callback(list_update, context))
    run_async(bot_tt.user_action_del_callback(quick_update, context))

    list_call = list_update.callback_query.edit_message_text.await_args
    quick_call = quick_update.callback_query.edit_message_text.await_args
    assert list_call.args[0] == quick_call.args[0]
    assert list_call.kwargs["parse_mode"] == quick_call.kwargs["parse_mode"] == bot_tt.ParseMode.HTML
    assert _button_datas(list_call.kwargs["reply_markup"]) == _button_datas(
        quick_call.kwargs["reply_markup"]
    )
