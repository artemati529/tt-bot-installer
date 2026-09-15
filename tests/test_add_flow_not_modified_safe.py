"""Добавление пользователя, нажатие «Отмена» не должно кидать ошибку.

Причина: add_entry_cb/add_cancel_callback/add_prefix_choice/add_protocol_choice
редактируют карточку через голый q.edit_message_text(...), а не через
safe_edit_message_text(q, ...), который уже есть в файле и тихо глотает
BadRequest("Message is not modified"). Если Telegram считает новый текст
идентичным текущему (двойной тап, ретрай апдейта, два синхронизированных
клиента одного юзера) — голый вызов бросает исключение наружу,
traced_callback его перехватывает и логирует, но затем ре-рейзит, и оно
долетает до log_unhandled_error — пользователь видит «❌ Внутренняя ошибка»."""
from unittest.mock import AsyncMock

from telegram.error import BadRequest


def _not_modified_query(update):
    update.callback_query.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )
    return update.callback_query


def test_add_entry_cb_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("vpn:add")
    _not_modified_query(update)

    run_async(bot_tt.add_entry_cb(update, context))  # must not raise


def test_add_cancel_callback_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    context.bot.delete_message = AsyncMock()
    update = allowed_callback_update("addcancel")
    _not_modified_query(update)
    context.user_data["pending_add_username"] = "bob"

    run_async(bot_tt.add_cancel_callback(update, context))  # must not raise


def test_add_prefix_choice_cancel_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    context.bot.delete_message = AsyncMock()
    update = allowed_callback_update("addpref:cancel")
    _not_modified_query(update)

    run_async(bot_tt.add_prefix_choice(update, context))  # must not raise


def test_add_prefix_choice_reset_session_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("addpref:on")
    _not_modified_query(update)
    # no pending_add_username/password -> hits the "session reset" branch

    run_async(bot_tt.add_prefix_choice(update, context))  # must not raise


def test_add_prefix_choice_success_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("addpref:on")
    _not_modified_query(update)
    context.user_data["pending_add_username"] = "bob"
    context.user_data["pending_add_password"] = "hunter2"

    run_async(bot_tt.add_prefix_choice(update, context))  # must not raise


def test_add_protocol_choice_cancel_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    context.bot.delete_message = AsyncMock()
    update = allowed_callback_update("addproto:cancel")
    _not_modified_query(update)

    run_async(bot_tt.add_protocol_choice(update, context))  # must not raise


def test_add_protocol_choice_reset_session_survives_not_modified(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("addproto:h2")
    _not_modified_query(update)
    # no pending_add_username/password -> hits the "session reset" branch

    run_async(bot_tt.add_protocol_choice(update, context))  # must not raise


def test_add_protocol_choice_failure_survives_not_modified(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(
        bot_tt,
        "_add_user_bundle_sync",
        lambda *a: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    update = allowed_callback_update("addproto:h2")
    _not_modified_query(update)
    context.user_data["pending_add_username"] = "bob"
    context.user_data["pending_add_password"] = "hunter2"
    context.user_data["pending_add_random_prefix"] = False

    run_async(bot_tt.add_protocol_choice(update, context))  # must not raise
