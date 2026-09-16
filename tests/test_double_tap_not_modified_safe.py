"""Двойной тап на confirm/cancel (частый на нестабильной связи) шлёт тот же
callback_data дважды — второе edit_message_text с тем же текстом даёт
BadRequest("Message is not modified"). Раньше это било необработанным
исключением в лог и ложным "Внутренняя ошибка" сразу после удаления
юзера/перезагрузки — самых пугающих мест для такой ошибки."""
from unittest.mock import AsyncMock

from telegram.error import BadRequest


def _not_modified(update):
    update.callback_query.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )


def test_reboot_cancel_survives_double_tap(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("rbcancel")
    _not_modified(update)

    run_async(bot_tt.reboot_callback(update, context))  # must not raise


def test_delete_user_cancel_survives_double_tap(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("delcancel:alice")
    _not_modified(update)

    run_async(bot_tt.delete_user_callback(update, context))  # must not raise


def test_backup_confirm_no_survives_double_tap(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("bak:no")
    _not_modified(update)

    run_async(bot_tt.backup_confirm_callback(update, context))  # must not raise
