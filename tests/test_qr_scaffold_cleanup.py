"""Add-user scaffolding messages must be removed after QR delivery."""
from typing import ClassVar
from unittest.mock import AsyncMock, Mock


class FakeMessage:
    _next_id: ClassVar[list[int]] = [100]

    def __init__(self, chat_id=111111, text=""):
        self.chat_id = chat_id
        self.message_id = FakeMessage._next_id[0]
        FakeMessage._next_id[0] += 1
        self.text = text
        self.reply_text = AsyncMock()
        self.reply_photo = AsyncMock()
        self.delete = AsyncMock()


def test_reply_deeplink_with_qr_deletes_source_when_asked(bot_tt, run_async):
    msg = FakeMessage()

    run_async(
        bot_tt.reply_deeplink_with_qr(
            msg,
            username="alice",
            deeplink="tt://?fake",
            action_label="создание пользователя",
            png=b"fake-png",
            delete_source=True,
        )
    )

    msg.delete.assert_awaited_once()


def test_reply_deeplink_with_qr_keeps_source_by_default(bot_tt, run_async):
    msg = FakeMessage()

    run_async(
        bot_tt.reply_deeplink_with_qr(
            msg,
            username="alice",
            deeplink="tt://?fake",
            action_label="повтор QR",
            png=b"fake-png",
        )
    )

    msg.delete.assert_not_called()


def test_add_user_flow_cleans_up_scaffold_after_qr(bot_tt, allowed_update, allowed_callback_update, context, run_async, monkeypatch):
    context.bot.delete_message = AsyncMock()
    monkeypatch.setattr(bot_tt, "_add_user_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", lambda *a, **k: None)

    # Entry prompt.
    entry_prompt_msg = FakeMessage()
    entry_update = allowed_callback_update("vpn:add")
    entry_update.callback_query.message = entry_prompt_msg
    run_async(bot_tt.add_entry_cb(entry_update, context))

    # Username step.
    username_msg = FakeMessage(text="bob")
    ask_password_msg = FakeMessage()
    username_msg.reply_text.return_value = ask_password_msg
    update1 = allowed_update("bob")
    update1.message = username_msg
    run_async(bot_tt.add_username(update1, context))

    # Password step.
    password_msg = FakeMessage(text="hunter2")
    chooser_msg = FakeMessage()
    password_msg.reply_text.return_value = chooser_msg
    update2 = allowed_update("hunter2")
    update2.message = password_msg
    run_async(bot_tt.add_password(update2, context))

    # Prefix and protocol steps.
    prefix_update = allowed_callback_update("addpref:off")
    prefix_update.callback_query.message = chooser_msg
    run_async(bot_tt.add_prefix_choice(prefix_update, context))

    proto_update = allowed_callback_update("addproto:h2")
    proto_update.callback_query.message = chooser_msg
    run_async(bot_tt.add_protocol_choice(proto_update, context))

    deleted_ids = {c.kwargs["message_id"] for c in context.bot.delete_message.call_args_list}
    assert entry_prompt_msg.message_id in deleted_ids
    assert username_msg.message_id in deleted_ids
    assert ask_password_msg.message_id in deleted_ids
    assert password_msg.message_id in deleted_ids
    # The chooser card is removed through the source message object.
    chooser_msg.delete.assert_awaited_once()


def test_export_protocol_cleans_up_protocol_choice_after_qr(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch
):
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", lambda *a, **k: None)

    chooser_msg = FakeMessage()
    update = allowed_callback_update("expproto:h2:bob")
    update.callback_query.message = chooser_msg

    run_async(bot_tt.export_protocol_callback(update, context))

    chooser_msg.reply_photo.assert_awaited_once()
    chooser_msg.delete.assert_awaited_once()


def test_export_protocol_does_not_persist_chosen_protocol(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch
):
    save_profile = Mock()
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", save_profile)

    chooser_msg = FakeMessage()
    update = allowed_callback_update("expproto:quic:bob")
    update.callback_query.message = chooser_msg

    run_async(bot_tt.export_protocol_callback(update, context))

    chooser_msg.reply_photo.assert_awaited_once()
    save_profile.assert_not_called()


def test_quick_qr_cleans_up_user_card_after_qr(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    monkeypatch.setattr(bot_tt, "_export_context_for_username", lambda username: ("", "h2"))
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))

    user_card = FakeMessage()
    update = allowed_callback_update("uqr:bob")
    update.callback_query.message = user_card

    run_async(bot_tt.user_quick_qr_callback(update, context))

    user_card.reply_photo.assert_awaited_once()
    user_card.delete.assert_awaited_once()
