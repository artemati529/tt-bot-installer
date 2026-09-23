"""Карточка прогресса обновления ОС/TT — это то же UI-сообщение: «🏠 Меню»
(upsert_ui_message(force_new=True)) удаляло его, а фоновые правки итога
(«✅ Готово», «❌ … бинарник восстановлен») уходили в удалённое сообщение —
итог терялся молча. Теперь карточка при старте отвязывается от UI."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture()
def no_bg(bot_tt, monkeypatch, tt_paths):
    monkeypatch.setattr(bot_tt, "_schedule_background_task", lambda ctx, coro: coro.close())
    yield
    bot_tt.busy_clear()


def _bot(context):
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=500, chat_id=111111))


def test_menu_during_os_upgrade_keeps_progress_card(bot_tt, no_bg, context, run_async):
    _bot(context)
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 10

    run_async(bot_tt.run_os_upgrade(context.bot, 111111, context=context))
    assert context.user_data.get(bot_tt.UI_MESSAGE_ID_KEY) != 10

    run_async(bot_tt.upsert_ui_message(context, 111111, "home", force_new=True))

    deleted = [c.kwargs.get("message_id") for c in context.bot.delete_message.await_args_list]
    assert 10 not in deleted


def test_tt_upgrade_card_detached_from_ui(bot_tt, no_bg, allowed_callback_update, context, run_async):
    _bot(context)
    update = allowed_callback_update("ttupd_yes")
    card_id = update.callback_query.message.message_id
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = card_id
    context.user_data["pending_tt_update"] = {"current": "1.0.0", "latest": "v1.2.3"}

    run_async(bot_tt.update_tt_callback(update, context))

    assert context.user_data.get(bot_tt.UI_MESSAGE_ID_KEY) != card_id
