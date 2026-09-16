"""Navigating to an unrelated callback route must cancel a stray add-user flow.

Repro: start "add user", reach ASK_ADD_PASSWORD, then tap a route that has
nothing to do with the add flow (e.g. rotate password for another user)
instead of typing the password. Only nav:*/start/cancel used to call
cancel_add_flow via reset_nav_state — every other CALLBACK_ROUTES entry left
add_flow_active/pending_add_username dangling, so PTB's still-active
ConversationHandler would later treat the rotate-password text as if it were
the abandoned add-flow's password."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import CommandHandler

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
    """Handlers registered in the same relative order as main(): the add
    conversation first, then the CALLBACK_ROUTES table (built the same way
    main() builds it, through build_callback_query_handler)."""
    conv = bot_tt.build_add_conversation()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=BOT)
    app_mock = MagicMock()
    route = next(r for r in bot_tt.CALLBACK_ROUTES if r.name == "user_action_rotate_callback")
    handlers = [
        CommandHandler("start", bot_tt.start),
        CommandHandler("cancel", bot_tt.cancel),
        conv,
        bot_tt.build_callback_query_handler(route),
    ]

    async def drive(update):
        for h in handlers:
            check = h.check_update(update)
            if check is not None:
                await h.handle_update(update, app_mock, check, ctx)
                return
        raise AssertionError(f"никто не обработал: {update!r}")

    return SimpleNamespace(conv=conv, ctx=ctx, drive=drive)


def test_rotate_tap_during_add_flow_cancels_add_flow(bot_tt, harness, run_async):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("newuser", 2)))
    assert harness.ctx.user_data.get("pending_add_username") == "newuser"

    run_async(harness.drive(mk_cb("urot:someoneelse", 3)))

    assert "add_flow_active" not in harness.ctx.user_data
    assert "pending_add_username" not in harness.ctx.user_data
    assert harness.ctx.user_data.get("pending_rotate_username") == "someoneelse"


def test_stray_password_text_after_rotate_tap_ends_add_flow_gracefully(bot_tt, harness, run_async):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("newuser", 2)))
    run_async(harness.drive(mk_cb("urot:someoneelse", 3)))

    run_async(harness.drive(mk_msg("thenewpassword", 4)))

    assert "pending_add_username" not in harness.ctx.user_data
