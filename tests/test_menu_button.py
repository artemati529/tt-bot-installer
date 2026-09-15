"""Persistent «🏠 Меню» reply-keyboard button.

ReplyKeyboardMarkup держится в чате, пока жив её носитель — носитель нельзя
удалять/пересылать на каждом заходе, поэтому шлётся только один раз, при
/start; тап «Меню» его не пересылает.

Отдельно — реальный прогон через ConversationHandler (не мок в лоб): тап
«Меню» посреди сценария добавления пользователя должен корректно оборвать
диалог, а не быть проглоченным как username.
"""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

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
    """group=-1 (кнопка «Меню») и group=0 (всё остальное) — оба реально
    получают апдейт в PTB (group stop только через ApplicationHandlerStop,
    его тут никто не бросает), поэтому drive() даёт шанс обеим группам,
    а не останавливается на первом совпадении."""
    conv = bot_tt.build_add_conversation()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=BOT)
    app_mock = MagicMock()
    menu_handler = MessageHandler(filters.Text(["🏠 Меню"]), bot_tt.menu_button_tap)
    group0 = [
        CommandHandler("start", bot_tt.start),
        CommandHandler("cancel", bot_tt.cancel),
        conv,
        CallbackQueryHandler(bot_tt.nav_callback, pattern=r"^nav:"),
    ]

    async def drive(update):
        ran = False
        menu_check = menu_handler.check_update(update)
        if menu_check:
            await menu_handler.handle_update(update, app_mock, menu_check, ctx)
            ran = True
        for h in group0:
            check = h.check_update(update)
            if check:
                await h.handle_update(update, app_mock, check, ctx)
                ran = True
                break
        if not ran:
            raise AssertionError(f"никто не обработал: {update!r}")

    return SimpleNamespace(conv=conv, ctx=ctx, drive=drive)


def test_menu_button_tap_kills_active_add_conversation(bot_tt, harness, run_async):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    assert harness.ctx.user_data.get("add_flow_active") is True
    run_async(harness.drive(mk_msg("🏠 Меню", 2)))
    assert "add_flow_active" not in harness.ctx.user_data
    assert "pending_add_username" not in harness.ctx.user_data


def test_menu_button_tap_is_not_captured_as_username(bot_tt, harness, run_async):
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("🏠 Меню", 2)))
    assert harness.ctx.user_data.get("pending_add_username") != "🏠 Меню"


def test_menu_button_tap_shows_home_screen(bot_tt, context, run_async):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    context.bot.edit_message_text = AsyncMock()
    update = mk_msg("🏠 Меню", 1)

    run_async(bot_tt.menu_button_tap(update, context))

    context.bot.send_message.assert_awaited()
    kwargs = context.bot.send_message.await_args.kwargs
    assert not isinstance(kwargs.get("reply_markup"), bot_tt.ReplyKeyboardMarkup), (
        "тап «Меню» не должен пересылать носитель клавиатуры заново"
    )


def test_start_attaches_persistent_menu_keyboard(bot_tt, allowed_update, context, run_async):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    context.bot.edit_message_text = AsyncMock()

    run_async(bot_tt.start(allowed_update(""), context))

    keyboard_calls = [
        c
        for c in context.bot.send_message.call_args_list
        if isinstance(c.kwargs.get("reply_markup"), bot_tt.ReplyKeyboardMarkup)
    ]
    assert keyboard_calls, "/start должен прикрепить постоянную клавиатуру «Меню»"


def test_start_never_deletes_the_keyboard_carrier(bot_tt, allowed_update, context, run_async):
    carrier = MagicMock(message_id=1)
    carrier.delete = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=carrier)
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()

    run_async(bot_tt.start(allowed_update(""), context))

    carrier.delete.assert_not_called()
    context.bot.delete_message.assert_not_called()
