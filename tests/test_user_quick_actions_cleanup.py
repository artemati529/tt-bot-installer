"""User quick actions must not leave the source card with live buttons."""
from unittest.mock import AsyncMock


class FakeMessage:
    def __init__(self, chat_id=111111, message_id=1):
        self.chat_id = chat_id
        self.message_id = message_id
        self.reply_text = AsyncMock()
        self.reply_photo = AsyncMock()
        self.delete = AsyncMock()


def _patch_user_exports(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda username: {"protocol": "h2", "random_prefix": False})
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda *a: ("tt://alice", b"png"))
    monkeypatch.setattr(bot_tt, "_export_toml_bundle_sync", lambda *a: ("trusttunnel-alice.toml", b"toml"))


def test_quick_toml_deletes_source_card(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    _patch_user_exports(bot_tt, monkeypatch)
    context.bot.send_document = AsyncMock()
    source = FakeMessage()
    update = allowed_callback_update("utc:alice")
    update.callback_query.message = source

    run_async(bot_tt.user_action_toml_callback(update, context))

    context.bot.send_document.assert_awaited_once()
    assert context.bot.send_document.await_args.kwargs["disable_notification"] is True
    source.delete.assert_awaited_once()


def test_quick_link_deletes_source_card(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    _patch_user_exports(bot_tt, monkeypatch)
    source = FakeMessage()
    update = allowed_callback_update("ulink:alice")
    update.callback_query.message = source

    run_async(bot_tt.user_action_link_callback(update, context))

    context.bot.send_message.assert_awaited_once()
    source.delete.assert_awaited_once()


def test_quick_all_deletes_source_card(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    _patch_user_exports(bot_tt, monkeypatch)
    context.bot.send_document = AsyncMock()
    source = FakeMessage()
    update = allowed_callback_update("uall:alice")
    update.callback_query.message = source

    run_async(bot_tt.user_action_all_callback(update, context))

    source.reply_photo.assert_awaited_once()
    context.bot.send_document.assert_awaited_once()
    assert context.bot.send_document.await_args.kwargs["disable_notification"] is True
    context.bot.send_message.assert_awaited_once()
    source.delete.assert_awaited_once()


def test_quick_rotate_deletes_source_card(bot_tt, allowed_callback_update, context, run_async):
    source = FakeMessage()
    update = allowed_callback_update("urot:alice")
    update.callback_query.message = source

    run_async(bot_tt.user_action_rotate_callback(update, context))

    context.bot.send_message.assert_awaited_once()
    source.delete.assert_awaited_once()
