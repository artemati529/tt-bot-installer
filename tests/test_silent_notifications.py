"""Bot-originated messages should not trigger Telegram sound/vibration."""
import inspect
from unittest.mock import AsyncMock, Mock


def test_application_defaults_disable_notifications(bot_tt):
    src = inspect.getsource(bot_tt.main)

    assert "Defaults(disable_notification=True)" in src
    assert ".defaults(" in src


def test_legacy_toml_export_document_is_silent(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda username: {"random_prefix": False})
    monkeypatch.setattr(bot_tt, "_export_toml_bundle_sync", lambda *a: ("trusttunnel-alice.toml", b"toml"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", lambda *a, **k: None)
    context.bot.send_document = AsyncMock()
    update = allowed_callback_update("tp:h2:alice")

    run_async(bot_tt.toml_export_callback(update, context))

    context.bot.send_document.assert_awaited_once()
    assert context.bot.send_document.await_args.kwargs["disable_notification"] is True


def test_legacy_toml_export_does_not_persist_chosen_protocol(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    save_profile = Mock()
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda username: {"random_prefix": False})
    monkeypatch.setattr(bot_tt, "_export_toml_bundle_sync", lambda *a: ("trusttunnel-alice.toml", b"toml"))
    monkeypatch.setattr(bot_tt, "_set_user_profile", save_profile)
    context.bot.send_document = AsyncMock()
    update = allowed_callback_update("tp:quic:alice")

    run_async(bot_tt.toml_export_callback(update, context))

    context.bot.send_document.assert_awaited_once()
    save_profile.assert_not_called()
