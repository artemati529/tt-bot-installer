"""user_action_qr_callback was the only user_action_* handler with no
"username exists?" guard — it built/sent a QR for a nonexistent user instead
of showing the same "Пользователь не найден" alert as _toml/_link/_all."""
from unittest.mock import AsyncMock


class FakeMessage:
    def __init__(self, chat_id=111111, message_id=1):
        self.chat_id = chat_id
        self.message_id = message_id
        self.reply_text = AsyncMock()
        self.reply_photo = AsyncMock()
        self.delete = AsyncMock()


def test_quick_qr_alerts_on_unknown_user(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    source = FakeMessage()
    update = allowed_callback_update("uqr:ghost")
    update.callback_query.message = source

    run_async(bot_tt.user_action_qr_callback(update, context))

    source.reply_photo.assert_not_awaited()
    assert update.callback_query.answer.await_args.kwargs.get("show_alert") is True
