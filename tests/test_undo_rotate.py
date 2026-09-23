"""Ротация пароля: успех вешает pending_undo("rotate_password", old_password)
и добавляет кнопку «Отменить» на карточку с deeplink."""
import re
from unittest.mock import AsyncMock


def test_rotate_success_sets_pending_undo_with_old_password(
    bot_tt, tt_paths, allowed_update, context, run_async, monkeypatch,
):
    (tt_paths["CRED_FILE"]).write_text(
        '[[client]]\nusername = "alice"\npassword = "old-pass"\n', encoding="utf-8"
    )
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")
    monkeypatch.setattr(bot_tt, "_export_context_for_username", lambda u: ("", "h2"))
    monkeypatch.setattr(bot_tt, "generate_deeplink", lambda *a, **k: "tt://?x")
    monkeypatch.setattr(bot_tt, "deeplink_qr_png", lambda dl: b"png")

    context.user_data["pending_rotate_username"] = "alice"
    update = allowed_update("new-pass")
    update.message.delete = AsyncMock()
    update.message.reply_photo = AsyncMock()

    run_async(bot_tt.rotate_password_input(update, context))

    info = bot_tt._pop_pending_undo(context)
    assert info == {"kind": "rotate_password", "payload": {"username": "alice", "old_password": "old-pass"}}

    kb = update.message.reply_photo.call_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    # Кнопка несёт токен своего действия, а не общий undo:go.
    assert any(re.fullmatch(r"undo:[0-9a-f]{8}", b or "") for b in buttons)


def test_rotate_failure_does_not_set_pending_undo(
    bot_tt, tt_paths, allowed_update, context, run_async,
):
    context.user_data["pending_rotate_username"] = "ghost"
    update = allowed_update("new-pass")
    update.message.delete = AsyncMock()
    update.message.reply_text = AsyncMock()

    run_async(bot_tt.rotate_password_input(update, context))

    assert bot_tt._pop_pending_undo(context) is None
