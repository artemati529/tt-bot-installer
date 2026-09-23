"""Ввод нового пароля (текстовый хендлер группы 10) шёл мимо busy:
во время обновления ОС ротация делала systemctl restart trusttunnel.
Теперь — отказ «Жди», пароль НЕ применяется, но сообщение с паролем
всё равно сгорает, а ожидание остаётся, чтобы отправить его ещё раз."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture()
def busy(bot_tt, tt_paths):
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "alice"\npassword = "old"\n', encoding="utf-8")
    bot_tt.busy_set("обновление ОС")
    yield
    bot_tt.busy_clear()


def test_rotate_input_rejected_while_busy(bot_tt, busy, allowed_update, context, run_async, monkeypatch):
    apply_mock = MagicMock(return_value=(None, None))
    monkeypatch.setattr(bot_tt, "_apply_rotate_password_sync", apply_mock)
    context.user_data["pending_rotate_username"] = "alice"
    update = allowed_update("new-secret")
    update.message.delete = AsyncMock()

    run_async(bot_tt.rotate_password_input(update, context))

    apply_mock.assert_not_called()
    update.message.delete.assert_awaited_once()
    assert "Жди" in update.message.reply_text.await_args.args[0]
    assert context.user_data.get("pending_rotate_username") == "alice"
