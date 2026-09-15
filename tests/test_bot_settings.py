"""Legacy post-create delivery settings must stay removed."""
import inspect
from unittest.mock import AsyncMock


def _datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_legacy_settings_api_is_removed(bot_tt):
    assert not hasattr(bot_tt, "settings_text")
    assert not hasattr(bot_tt, "settings_inline_kb")
    assert not hasattr(bot_tt, "settings_callback")
    assert not hasattr(bot_tt, "load_bot_settings")
    assert not hasattr(bot_tt, "save_bot_settings")
    assert not hasattr(bot_tt, "BOT_SETTINGS_FILE")
    assert not hasattr(bot_tt, "DEFAULT_BOT_SETTINGS")


def test_settings_callback_is_not_registered(bot_tt):
    src = inspect.getsource(bot_tt.main)

    assert "settings_callback" not in src
    assert 'pattern=r"^set:"' not in src


def test_create_flow_sends_one_qr_card(
    bot_tt, tt_paths, allowed_update, allowed_callback_update, context, run_async, monkeypatch
):
    context.bot.delete_message = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_message = AsyncMock()
    monkeypatch.setattr(bot_tt, "_add_user_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))
    monkeypatch.setattr(bot_tt, "_export_toml_bundle_sync", lambda *a: ("trusttunnel-bob.toml", b"toml"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", lambda *a, **k: None)

    class Msg:
        chat_id = 111111
        message_id = 10
        reply_photo = AsyncMock()
        delete = AsyncMock()

    context.user_data["pending_add_username"] = "bob"
    context.user_data["pending_add_password"] = "secret"
    context.user_data["pending_add_random_prefix"] = False
    update = allowed_callback_update("addproto:h2")
    update.callback_query.message = Msg()

    run_async(bot_tt.add_protocol_choice(update, context))

    Msg.reply_photo.assert_awaited_once()
    context.bot.send_document.assert_not_awaited()
    context.bot.send_message.assert_not_awaited()


def test_create_flow_always_sends_qr_card(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch
):
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock()
    monkeypatch.setattr(bot_tt, "_add_user_bundle_sync", lambda *a: ("tt://?fake", b"fake-png"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", lambda *a, **k: None)

    class Msg:
        chat_id = 111111
        message_id = 10
        reply_photo = AsyncMock()
        delete = AsyncMock()

    context.user_data["pending_add_username"] = "bob"
    context.user_data["pending_add_password"] = "secret"
    context.user_data["pending_add_random_prefix"] = False
    context.user_data["add_flow_scaffold"] = [(111111, 10)]
    update = allowed_callback_update("addproto:h2")
    update.callback_query.message = Msg()

    run_async(bot_tt.add_protocol_choice(update, context))

    Msg.reply_photo.assert_awaited_once()
    Msg.delete.assert_awaited_once()
    context.bot.send_message.assert_not_awaited()


def test_server_hub_has_no_settings_button(bot_tt):
    datas = _datas(bot_tt.server_hub_kb())

    assert "nav:settings" not in datas
