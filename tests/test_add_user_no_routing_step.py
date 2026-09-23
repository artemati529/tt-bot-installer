"""Protocol choice must finish the add-user flow."""
from unittest.mock import AsyncMock


class FakeMessage:
    def __init__(self, chat_id=111111, message_id=1):
        self.chat_id = chat_id
        self.message_id = message_id
        self.reply_photo = AsyncMock()
        self.delete = AsyncMock()
        self.edit_text = AsyncMock()


def test_add_protocol_choice_creates_user_and_ends_conversation(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    monkeypatch.setattr(bot_tt, "_add_user_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", lambda *a, **k: None)
    context.user_data["pending_add_username"] = "bob"
    context.user_data["pending_add_password"] = "hunter2"
    context.user_data["pending_add_random_prefix"] = False

    update = allowed_callback_update("addproto:h2")
    update.callback_query.message = FakeMessage()

    result = run_async(bot_tt.add_protocol_choice(update, context))

    assert result == bot_tt.ConversationHandler.END
    update.callback_query.message.reply_photo.assert_awaited_once()
