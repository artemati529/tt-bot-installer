"""Список экранов, которые редактируют q.message
напрямую (users_page_callback/users_filter_callback/clients_page_callback/
rules_sync_callback), не обновляли UI_MESSAGE_ID_KEY. Если где-то ещё
(например send_ui_card с force_new=True для совсем другого сценария)
"текущим" считается устаревший id, следующий upsert_ui_message отредактирует
не то сообщение, а живой экран останется с чужими кнопками. Все четыре
хендлера теперь синхронизируют UI_MESSAGE_ID_KEY на своё q.message при
каждой успешной отрисовке — тот же инвариант, что уже держит nav_callback.
"""
from unittest.mock import AsyncMock


def test_users_page_callback_remembers_its_message(bot_tt, allowed_callback_update, context, run_async, tt_paths):
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 999  # устаревший, чужой id
    update = allowed_callback_update("ul:0")
    update.callback_query.message.message_id = 42
    update.callback_query.edit_message_text = AsyncMock()

    run_async(bot_tt.users_page_callback(update, context))

    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 42


def test_users_filter_callback_remembers_its_message(bot_tt, allowed_callback_update, context, run_async, tt_paths):
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 999
    update = allowed_callback_update("uf:all")
    update.callback_query.message.message_id = 43
    update.callback_query.edit_message_text = AsyncMock()

    run_async(bot_tt.users_filter_callback(update, context))

    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 43


def test_clients_page_callback_remembers_its_message(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "clients_card_html", lambda page: ("<b>x</b>", 1, [], False))
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 999
    update = allowed_callback_update("ss:0")
    update.callback_query.message.message_id = 44
    update.callback_query.edit_message_text = AsyncMock()

    run_async(bot_tt.clients_page_callback(update, context))

    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 44


def test_rules_sync_callback_remembers_its_message(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "build_rules_sync_report", lambda: "report")
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 999
    update = allowed_callback_update("rulesync:view")
    update.callback_query.message.message_id = 45
    update.callback_query.edit_message_text = AsyncMock()

    run_async(bot_tt.rules_sync_callback(update, context))

    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 45
