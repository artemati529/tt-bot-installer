"""delete_user_callback (deldo:) должен захватить пароль/профиль ДО удаления
и повесить кнопку «Отменить»."""


def test_deldo_success_sets_pending_undo(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    (tt_paths["CRED_FILE"]).write_text(
        '[[client]]\nusername = "alice"\npassword = "secret"\n'
        '[[client]]\nusername = "bob"\npassword = "b"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")
    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: "active")
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda u: {"protocol": "quic", "random_prefix": False})

    update = allowed_callback_update("deldo:alice")
    run_async(bot_tt.delete_user_callback(update, context))

    info = bot_tt._pop_pending_undo(context)
    assert info["kind"] == "delete_user"
    assert info["payload"]["username"] == "alice"
    assert info["payload"]["password"] == "secret"
    assert "protocol" not in info["payload"]

    kb = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "undo:go" in buttons


def test_deldo_missing_user_does_not_set_pending_undo(bot_tt, tt_paths, allowed_callback_update, context, run_async):
    (tt_paths["CRED_FILE"]).write_text('[[client]]\nusername = "bob"\npassword = "b"\n', encoding="utf-8")

    update = allowed_callback_update("deldo:ghost")
    run_async(bot_tt.delete_user_callback(update, context))

    assert bot_tt._pop_pending_undo(context) is None
