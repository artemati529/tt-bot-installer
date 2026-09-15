"""run_rotate_pick/run_export_pick/run_user_delete_list — общий run_user_pick,
все три переживают падение list_usernames()."""
from unittest.mock import AsyncMock, MagicMock


def _mock_bot(context):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))


def test_rotate_pick_survives_list_usernames_failure(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)

    def boom():
        raise RuntimeError("credentials.toml unreadable")

    monkeypatch.setattr(bot_tt, "list_usernames", boom)

    run_async(bot_tt.run_rotate_pick(context.bot, 111111, context))

    context.bot.send_message.assert_called_once()
    text = context.bot.send_message.call_args.kwargs["text"]
    assert "Не удалось получить список пользователей" in text


def test_export_pick_survives_list_usernames_failure(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)

    def boom():
        raise RuntimeError("credentials.toml unreadable")

    monkeypatch.setattr(bot_tt, "list_usernames", boom)

    run_async(bot_tt.run_export_pick(context.bot, 111111, context=context))

    context.bot.send_message.assert_called_once()
    text = context.bot.send_message.call_args.kwargs["text"]
    assert "Не удалось получить список пользователей" in text


def test_delete_list_buttons_one_per_row(bot_tt, context, run_async, monkeypatch):
    """Одна строка на всех при 7 юзернеймах сжимает кнопки до нечитаемого
    "🗑 …" — как и rotate/export, один пользователь — одна строка."""
    _mock_bot(context)
    users = ["alice", "bob", "charlie", "dave", "erin", "frank", "grace"]
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: users)

    run_async(bot_tt.run_user_delete_list(context.bot, 111111, context=context))

    kb = context.bot.send_message.call_args.kwargs["reply_markup"]
    user_rows = kb.inline_keyboard[: len(users)]
    assert [len(row) for row in user_rows] == [1] * len(users)
    assert [row[0].text for row in user_rows] == [f"🗑 {u}" for u in users]


def test_rotate_pick_buttons_one_per_row(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice", "bob"])

    run_async(bot_tt.run_rotate_pick(context.bot, 111111, context))

    kb = context.bot.send_message.call_args.kwargs["reply_markup"]
    user_rows = kb.inline_keyboard[:2]
    assert [len(row) for row in user_rows] == [1, 1]
    assert [row[0].text for row in user_rows] == ["alice", "bob"]


def test_rotate_pick_clears_rotate_wait_before_listing(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    context.user_data["pending_rotate_username"] = "someone"

    run_async(bot_tt.run_rotate_pick(context.bot, 111111, context))

    assert "pending_rotate_username" not in context.user_data
