"""Сгорающие сообщения должны уходить по всем путям, не только по счастливому сценарию."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import CallbackQueryHandler, CommandHandler

USER = User(id=111111, is_bot=False, first_name="admin")
CHAT = Chat(id=111111, type="private")
BOT = AsyncMock()
BOT.username = "tt_bot"
BOT.id = 555


def mk_msg(text: str, mid: int, entity: bool = False) -> Update:
    ents = [MessageEntity(type="bot_command", offset=0, length=len(text))] if entity else None
    msg = Message(message_id=mid, date=dt.datetime.now(dt.UTC), chat=CHAT, from_user=USER, text=text, entities=ents)
    msg.set_bot(BOT)
    return Update(update_id=mid, message=msg)


def mk_cb(data: str, uid: int) -> Update:
    msg = Message(message_id=uid, date=dt.datetime.now(dt.UTC), chat=CHAT, from_user=USER)
    msg.set_bot(BOT)
    cq = CallbackQuery(id=str(uid), from_user=USER, chat_instance="1", data=data, message=msg)
    cq.set_bot(BOT)
    return Update(update_id=uid, callback_query=cq)


def _harness_for(bot_tt, monkeypatch):
    conv = bot_tt.build_add_conversation()
    ctx = SimpleNamespace(user_data={}, chat_data={}, bot_data={}, bot=BOT)
    app_mock = MagicMock()
    handlers = [
        CommandHandler("start", bot_tt.start),
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

    return SimpleNamespace(conv=conv, ctx=ctx, drive=drive, handlers=handlers)


# ── A: add-флоу — scaffold чистится при внешнем прерывании ──────────────


def test_add_flow_deletes_credentials_on_external_interrupt(
    bot_tt, monkeypatch, run_async,
):
    """If the user starts a user flow and leaves (start/cancel/nav),
    the entered username and password must be deleted."""
    BOT.send_message = AsyncMock(side_effect=[
        MagicMock(message_id=4, chat_id=111111),  # add_username → ask_password
        MagicMock(message_id=5, chat_id=111111),  # add_password → params card
        MagicMock(message_id=6, chat_id=111111),  # /start → persistent menu
        MagicMock(message_id=7, chat_id=111111),  # send_home_screen
    ])

    harness = _harness_for(bot_tt, monkeypatch)

    # ➕ Новый → username → password
    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("ivan", 2)))
    run_async(harness.drive(mk_msg("hunter2", 3)))

    # External interrupt: /start
    run_async(harness.drive(mk_msg("/start", 4, entity=True)))

    deleted = {c.kwargs["message_id"] for c in BOT.delete_message.call_args_list}
    assert 2 in deleted, "введённый username должен сгореть"
    assert 3 in deleted, "введённый пароль должен сгореть"


def test_add_flow_deletes_credentials_on_cancel(
    bot_tt, monkeypatch, run_async,
):
    """External /cancel also cleans up the scaffold."""
    BOT.send_message = AsyncMock(side_effect=[
        MagicMock(message_id=4, chat_id=111111),  # add_username → ask_password
        MagicMock(message_id=5, chat_id=111111),  # add_password → params card
        MagicMock(message_id=6, chat_id=111111),  # /cancel → "Ввод отменён"
    ])

    harness = _harness_for(bot_tt, monkeypatch)

    run_async(harness.drive(mk_cb("vpn:add", 1)))
    run_async(harness.drive(mk_msg("bob", 2)))
    run_async(harness.drive(mk_msg("secret", 3)))

    run_async(harness.drive(mk_msg("/cancel", 4, entity=True)))

    deleted = {c.kwargs["message_id"] for c in BOT.delete_message.call_args_list}
    assert 2 in deleted
    assert 3 in deleted


# ── B: ротация пароля — сообщение с паролем сгорает на любом пути ──────


def test_rotate_input_burns_password_on_error(
    bot_tt, allowed_update, context, run_async, monkeypatch,
):
    monkeypatch.setattr(
        bot_tt, "_apply_rotate_password_sync",
        lambda u, p: ("Пользователь 'ghost' не найден.", None),
    )
    context.user_data["pending_rotate_username"] = "ghost"
    update = allowed_update("brand-new-pass")
    update.message.delete = AsyncMock()

    run_async(bot_tt.rotate_password_input(update, context))

    update.message.delete.assert_awaited_once()


def test_rotate_input_burns_password_on_success(
    bot_tt, allowed_update, context, run_async, monkeypatch,
):
    monkeypatch.setattr(
        bot_tt, "_apply_rotate_password_sync",
        lambda u, p: (None, ("u", "dl", b"p")),
    )
    context.user_data["pending_rotate_username"] = "alice"
    update = allowed_update("new123")
    update.message.delete = AsyncMock()
    update.message.reply_photo = AsyncMock()
    context.bot.send_inline_message = AsyncMock()

    run_async(bot_tt.rotate_password_input(update, context))

    update.message.delete.assert_awaited_once()


# ── C: промпт ротации — трекается и удаляется при выходе ───────────────


def test_urot_prompt_burned_on_nav(
    bot_tt, allowed_callback_update, context, run_async,
):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=100, chat_id=111111))
    context.bot.delete_message = AsyncMock()

    update = allowed_callback_update("urot:alice")
    run_async(bot_tt.user_quick_rotate_callback(update, context))

    scaffold = context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY]
    assert len(scaffold) == 1
    prompt_id = scaffold[0][1]
    assert prompt_id == 100

    nav = allowed_callback_update("nav:vpn")
    run_async(bot_tt.nav_callback(nav, context))

    context.bot.delete_message.assert_called_with(chat_id=111111, message_id=prompt_id)


def test_second_rotation_removes_first_prompt(
    bot_tt, allowed_callback_update, context, run_async,
):
    context.bot.send_message = AsyncMock(
        side_effect=[
            MagicMock(message_id=100, chat_id=111111),  # first prompt
            MagicMock(message_id=200, chat_id=111111),  # second prompt
        ]
    )
    context.bot.delete_message = AsyncMock()

    u1 = allowed_callback_update("urot:alice")
    run_async(bot_tt.user_quick_rotate_callback(u1, context))
    assert context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY] == [(111111, 100)]

    u2 = allowed_callback_update("urot:bob")
    run_async(bot_tt.user_quick_rotate_callback(u2, context))

    deleted = {c[1]["message_id"] for c in context.bot.delete_message.call_args_list}
    assert 100 in deleted
    assert len(context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY]) == 1


def test_urot_prompt_back_keeps_card(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch,
):
    # Два РАЗНЫХ сообщения: старая карточка пользователя (на которой нажали
    # "🔁 Сменить пароль") и новый промпт ротации, который бот шлёт отдельным
    # сообщением. Изначально тест ошибочно использовал один мок для обеих
    # ролей — из-за этого "промпт не удаляется" было неотличимо от "старая
    # карточка не удаляется", хотя у них разная судьба: карточка сгорает,
    # промпт переиспользуется (edit) под "⬅️ Назад".
    old_card = MagicMock(message_id=50, chat_id=111111)
    old_card.delete = AsyncMock()

    prompt_msg = MagicMock(message_id=100, chat_id=111111)
    prompt_msg.text = "prompt"
    prompt_msg.reply_text = AsyncMock()
    prompt_msg.delete = AsyncMock()
    prompt_msg.edit_message_text = AsyncMock()
    prompt_msg.edit_text = AsyncMock()

    context.bot.send_message = AsyncMock(return_value=prompt_msg)
    context.bot.delete_message = AsyncMock()
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda u: {})
    monkeypatch.setattr(bot_tt, "_export_context_for_username", lambda u: ("", "h2"))

    # Start urot: — tracks the new prompt, burns the old card
    urot_update = allowed_callback_update("urot:alice")
    urot_update.callback_query.message = old_card
    run_async(bot_tt.user_quick_rotate_callback(urot_update, context))

    assert context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY] == [(111111, 100)]

    # Press "⬅️ Назад" — prompt becomes a user card
    back_update = allowed_callback_update("udev:alice")
    back_update.callback_query.message = prompt_msg
    run_async(bot_tt.user_detail_callback(back_update, context))

    # Card is removed from scaffold — not deleted
    assert context.user_data.get(bot_tt.ROTATE_SCAFFOLD_KEY, []) == []
    prompt_msg.delete.assert_not_awaited()


# ── E: re-entry-ввод трекается и сгорает на отмене ─────────────────────


def test_invalid_username_burned_on_cancel(
    bot_tt, allowed_update, allowed_callback_update, context, run_async,
):
    context.bot.delete_message = AsyncMock()

    entry = allowed_callback_update("vpn:add")
    entry.callback_query.message.message_id = 10
    run_async(bot_tt.add_entry_cb(entry, context))

    bad = allowed_update("bad name!")
    bad.message.message_id = 20
    run_async(bot_tt.add_username(bad, context))

    cancel = allowed_callback_update("addcancel")
    cancel.callback_query.message.message_id = 30
    run_async(bot_tt.add_cancel_callback(cancel, context))

    deleted = {c[1]["message_id"] for c in context.bot.delete_message.call_args_list}
    assert 20 in deleted, "некорректный username должен сгореть"
