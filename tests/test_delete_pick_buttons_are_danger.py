"""Per-user delete-picker buttons should be styled danger; rotate/export
pickers (also built by run_user_pick) stay unstyled."""
from unittest.mock import AsyncMock, MagicMock


def test_delete_list_buttons_are_danger(bot_tt, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice", "bob"])
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

    run_async(bot_tt.run_user_delete_list(context.bot, 111111, context=context))

    kb = context.bot.send_message.await_args.kwargs["reply_markup"]
    buttons = [b for row in kb.inline_keyboard for b in row if b.callback_data.startswith("delask:")]
    assert buttons
    assert all(b.style == "danger" for b in buttons)


def test_rotate_list_buttons_are_not_danger(bot_tt, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

    run_async(bot_tt.run_rotate_pick(context.bot, 111111, context))

    kb = context.bot.send_message.await_args.kwargs["reply_markup"]
    buttons = [b for row in kb.inline_keyboard for b in row if b.callback_data.startswith("rotpick:")]
    assert buttons
    assert all(b.style is None for b in buttons)
