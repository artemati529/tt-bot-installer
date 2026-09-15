"""Invalid credentials.toml must render an error card."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User

USER = User(id=111111, is_bot=False, first_name="admin")
CHAT = Chat(id=111111, type="private")


@pytest.fixture()
def corrupt_creds(bot_tt, tt_paths):
    tt_paths["CRED_FILE"].write_text("username = \n", encoding="utf-8")


def mk_cb(data, bot_mock):
    msg = Message(message_id=1, date=dt.datetime.now(dt.UTC), chat=CHAT, from_user=USER)
    msg.set_bot(bot_mock)
    cq = CallbackQuery(id="1", from_user=USER, chat_instance="1", data=data, message=msg)
    cq.set_bot(bot_mock)
    return Update(update_id=1, callback_query=cq)


def _edited_text(bot_mock):
    assert bot_mock.edit_message_text.called, "сообщение не отредактировано"
    args, kwargs = bot_mock.edit_message_text.call_args
    return kwargs.get("text") or (args[0] if args else "")


def test_nav_users_shows_error_card_on_corrupt_credentials(bot_tt, corrupt_creds, run_async):
    bot_mock = AsyncMock()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=bot_mock)
    update = mk_cb("nav:users:0", bot_mock)

    run_async(bot_tt.nav_callback(update, ctx))

    assert "Не удалось показать список" in _edited_text(bot_mock)


def test_user_detail_shows_error_card_on_corrupt_credentials(bot_tt, corrupt_creds, run_async):
    bot_mock = AsyncMock()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=bot_mock)
    update = mk_cb("udev:ivan", bot_mock)

    run_async(bot_tt.user_detail_callback(update, ctx))

    assert "Не удалось показать карточку" in _edited_text(bot_mock)
