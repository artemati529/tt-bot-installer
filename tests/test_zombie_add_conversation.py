"""Navigation must cancel the active add-user conversation.

Раньше cancel_add_flow дотягивался до приватного PTB API
(conv._conversations/conv._get_key) чтобы форсировать конец диалога извне.
Теперь используется тот же паттерн, что уже был в user_search_text/
rotate_password_input: публичный флаг в user_data (add_flow_active),
который add_username сам проверяет и явно завершает диалог (return
ConversationHandler.END), если флаг снят снаружи."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import CallbackQueryHandler, CommandHandler

USER = User(id=111111, is_bot=False, first_name="admin")
CHAT = Chat(id=111111, type="private")
BOT = AsyncMock()
BOT.username = "tt_bot"
BOT.id = 555


def mk_msg(text, mid, entity=False):
    ents = [MessageEntity(type="bot_command", offset=0, length=len(text))] if entity else None
    msg = Message(message_id=mid, date=dt.datetime.now(dt.UTC), chat=CHAT, from_user=USER, text=text, entities=ents)
    msg.set_bot(BOT)
    return Update(update_id=mid, message=msg)


def mk_cb(data, uid):
    msg = Message(message_id=uid, date=dt.datetime.now(dt.UTC), chat=CHAT, from_user=USER)
    msg.set_bot(BOT)
    cq = CallbackQuery(id=str(uid), from_user=USER, chat_instance="1", data=data, message=msg)
    cq.set_bot(BOT)
    return Update(update_id=uid, callback_query=cq)


@pytest.fixture()
def harness(bot_tt):
    """Handlers registered in the same relative order as main()."""
    conv = bot_tt.build_add_conversation()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=BOT)
    app_mock = MagicMock()
    handlers = [
        CommandHandler("start", bot_tt.start),
        CommandHandler("myid", bot_tt.myid),
        CommandHandler("cancel", bot_tt.cancel),
        conv,
        CallbackQueryHandler(bot_tt.nav_callback, pattern=r"^nav:"),
    ]

    async def drive(update):
        for h in handlers:
            check = h.check_update(update)
            if check is not None:
                await h.handle_update(update, app_mock, check, ctx)
                return
        raise AssertionError(f"никто не обработал: {update!r}")

    return SimpleNamespace(conv=conv, ctx=ctx, drive=drive)


def test_add_flow_still_works(bot_tt, harness, run_async):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    assert harness.ctx.user_data.get("add_flow_active") is True
    run_async(harness.drive(mk_msg("ivan", 2)))
    assert harness.ctx.user_data.get("pending_add_username") == "ivan"


@pytest.mark.parametrize(
    "make_escape_update",
    [
        lambda: mk_msg("/start", 2, entity=True),
        lambda: mk_msg("/cancel", 2, entity=True),
        lambda: mk_cb("nav:home", 2),
        lambda: mk_cb("nav:vpn", 2),
    ],
    ids=["start", "cancel", "nav_home", "nav_vpn"],
)
def test_escape_clears_add_flow_state(bot_tt, harness, run_async, make_escape_update):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    assert harness.ctx.user_data.get("add_flow_active") is True

    run_async(harness.drive(make_escape_update()))
    assert "add_flow_active" not in harness.ctx.user_data
    assert "pending_add_username" not in harness.ctx.user_data


@pytest.mark.parametrize(
    "make_escape_update",
    [
        lambda: mk_msg("/start", 2, entity=True),
        lambda: mk_cb("nav:home", 2),
    ],
    ids=["start", "nav_home"],
)
def test_stray_text_after_escape_is_not_treated_as_username(bot_tt, harness, run_async, make_escape_update):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(make_escape_update()))

    run_async(harness.drive(mk_msg("randomtext", 3)))
    assert "pending_add_username" not in harness.ctx.user_data


def test_nav_users_kills_active_add_conversation(bot_tt, tt_paths, harness, run_async):
    (tt_paths["CRED_FILE"]).write_text(
        '[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8"
    )
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    assert harness.ctx.user_data.get("add_flow_active") is True
    run_async(harness.drive(mk_cb("nav:users:0", 2)))
    assert "add_flow_active" not in harness.ctx.user_data
