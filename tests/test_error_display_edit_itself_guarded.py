"""В except-блоках, которые уже сообщают об ошибке, сам edit тоже может
упасть (сообщение успели удалить — "message to edit not found"). Раньше
эта вторая ошибка вылетала наружу необработанной, хотя основное действие
(например отправка файла) уже могло пройти успешно."""
from unittest.mock import AsyncMock

from telegram.error import BadRequest


def _message_not_found(update):
    update.callback_query.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message to edit not found")
    )


def test_export_protocol_command_error_display_does_not_raise(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    def boom(username, protocol):
        raise bot_tt.CommandError("boom")

    monkeypatch.setattr(bot_tt, "_export_bundle_sync", boom)
    update = allowed_callback_update("expproto:h2:alice")
    _message_not_found(update)

    run_async(bot_tt.export_protocol_callback(update, context))  # must not raise


def test_export_protocol_generic_error_display_does_not_raise(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    def boom(username, protocol):
        raise RuntimeError("boom")

    monkeypatch.setattr(bot_tt, "_export_bundle_sync", boom)
    update = allowed_callback_update("expproto:h2:alice")
    _message_not_found(update)

    run_async(bot_tt.export_protocol_callback(update, context))  # must not raise
