"""User search prompt should be cancellable without leaving service messages."""
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _button_datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def _button_texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def test_find_prompt_has_cancel_button_and_tracks_prompt(bot_tt, allowed_callback_update, context, run_async):
    sent_prompt = SimpleNamespace(chat_id=111111, message_id=42)
    context.bot.send_message.return_value = sent_prompt
    update = allowed_callback_update("vpn:find")

    run_async(bot_tt.vpn_hub_callback(update, context))

    kwargs = context.bot.send_message.await_args.kwargs
    kb = kwargs["reply_markup"]
    assert kb is not None
    assert "searchcancel" in _button_datas(kb)
    assert "❌ Отмена" in _button_texts(kb)
    assert context.user_data["pending_user_search"] is True
    assert context.user_data["user_search_scaffold"] == [(111111, 42)]


def test_find_cancel_deletes_prompt_and_clears_pending_search(
    bot_tt, allowed_callback_update, context, run_async
):
    cancel_cb = getattr(bot_tt, "user_search_cancel_callback", None)
    assert callable(cancel_cb)
    context.bot.delete_message = AsyncMock()
    context.user_data["pending_user_search"] = True
    context.user_data["user_search_scaffold"] = [(111111, 55)]
    update = allowed_callback_update("searchcancel")
    update.callback_query.message.chat_id = 111111
    update.callback_query.message.message_id = 55

    run_async(cancel_cb(update, context))

    assert "pending_user_search" not in context.user_data
    assert "user_search_scaffold" not in context.user_data
    context.bot.delete_message.assert_awaited_once_with(chat_id=111111, message_id=55)
    update.callback_query.edit_message_text.assert_not_awaited()
