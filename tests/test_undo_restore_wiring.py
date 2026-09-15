"""restore_backup_callback (resdo:) должен захватить содержимое файла ДО
восстановления и повесить кнопку «Отменить» — только для одиночного файла,
не для resdo:__all__."""


def test_resdo_single_file_sets_pending_undo(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    target = tt_paths["TT_DIR"] / "vpn.toml"
    target.write_text("live-before\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    target.write_text("live-changed\n", encoding="utf-8")

    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: "active")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")

    update = allowed_callback_update("resdo:vpn.toml")
    run_async(bot_tt.restore_backup_callback(update, context))

    info = bot_tt._pop_pending_undo(context)
    assert info == {"kind": "restore_file", "payload": {"filename": "vpn.toml", "data": b"live-changed\n", "mode": info["payload"]["mode"]}}

    kb = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "undo:go" in buttons


def test_resdo_all_does_not_set_pending_undo(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: "active")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")

    update = allowed_callback_update("resdo:__all__")
    run_async(bot_tt.restore_backup_callback(update, context))

    assert bot_tt._pop_pending_undo(context) is None
