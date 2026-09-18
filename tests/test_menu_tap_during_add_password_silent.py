"""Tapping "🏠 Меню" (or /start) while ASK_ADD_USERNAME already exits the
ConversationHandler silently (checks add_flow_active first) — ASK_ADD_PASSWORD
didn't have that same guard, so it fell into the "session lost" branch
and sent a confusing "Сессия сброшена" reply right alongside the home
screen the menu tap already showed, plus tracked the literal "🏠 Меню"
text message into the add-flow scaffold for no reason (nothing ever
cleans it up afterwards, since the conversation already ended).

PTB's group -1 (the menu handler) and the default group 0 (the add-flow
ConversationHandler) both process the same update independently — verified
directly against a real Application.process_update() — so by the time
add_password runs, group -1 has already cleared add_flow_active/
pending_add_username via reset_nav_state -> cancel_add_flow."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import CommandHandler, MessageHandler, filters

USER = User(id=111111, is_bot=False, first_name="admin")
CHAT = Chat(id=111111, type="private")
BOT = AsyncMock()
BOT.username = "tt_bot"
BOT.id = 555


def mk_msg(text, mid):
    msg = Message(message_id=mid, date=dt.datetime.now(dt.UTC), chat=CHAT, from_user=USER, text=text)
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
    """Same relative handler order as main(): the "🏠 Меню" handler at
    group -1, then the add-flow ConversationHandler at the default group."""
    conv = bot_tt.build_add_conversation()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=BOT)
    app_mock = MagicMock()
    menu_handler = MessageHandler(filters.Text(["🏠 Меню"]), bot_tt.allow_guard(bot_tt.menu_button_tap))
    handlers = [menu_handler, CommandHandler("start", bot_tt.start), CommandHandler("cancel", bot_tt.cancel), conv]

    async def drive(update):
        for h in handlers:
            check = h.check_update(update)
            if check:
                await h.handle_update(update, app_mock, check, ctx)

    return SimpleNamespace(conv=conv, ctx=ctx, drive=drive)


def test_menu_tap_during_ask_password_sends_no_extra_message(bot_tt, harness, run_async, monkeypatch, tt_paths):
    monkeypatch.setattr(bot_tt, "send_home_screen", AsyncMock())
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("newuser", 2)))
    BOT.send_message.reset_mock()

    run_async(harness.drive(mk_msg("🏠 Меню", 3)))

    BOT.send_message.assert_not_called()


def test_menu_tap_during_ask_password_does_not_track_the_tap_itself(bot_tt, harness, run_async, monkeypatch, tt_paths):
    monkeypatch.setattr(bot_tt, "send_home_screen", AsyncMock())
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("newuser", 2)))

    run_async(harness.drive(mk_msg("🏠 Меню", 3)))

    assert harness.ctx.user_data.get(bot_tt.ADD_FLOW_SCAFFOLD_KEY, []) == []
