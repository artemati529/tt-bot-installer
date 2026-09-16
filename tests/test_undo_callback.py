"""undo_callback: диспетчер по kind + сами реализации отмены."""
from unittest.mock import AsyncMock


def test_undo_callback_no_pending_undo(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("undo:go")
    run_async(bot_tt.undo_callback(update, context))
    text = update.callback_query.answer.call_args.kwargs.get("text") or ""
    assert "нечего" in text.lower()


def test_undo_rotate_password_restores_old_password(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch,
):
    (tt_paths["CRED_FILE"]).write_text(
        '[[client]]\nusername = "alice"\npassword = "new-pass"\n', encoding="utf-8"
    )
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")
    bot_tt._set_pending_undo(context, "rotate_password", {"username": "alice", "old_password": "old-pass"})

    update = allowed_callback_update("undo:go")
    update.callback_query.edit_message_caption = AsyncMock()
    run_async(bot_tt.undo_callback(update, context))

    text = (tt_paths["CRED_FILE"]).read_text(encoding="utf-8")
    assert "old-pass" in text
    assert "new-pass" not in text


def test_undo_delete_user_recreates_user(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch,
):
    (tt_paths["CRED_FILE"]).write_text('[[client]]\nusername = "bob"\npassword = "b"\n', encoding="utf-8")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")
    monkeypatch.setattr(bot_tt, "generate_deeplink", lambda *a, **k: "tt://?x")
    bot_tt._set_pending_undo(
        context, "delete_user",
        {"username": "alice", "password": "old-pass", "random_prefix": False, "protocol": "h2"},
    )

    update = allowed_callback_update("undo:go")
    run_async(bot_tt.undo_callback(update, context))

    usernames = bot_tt.list_usernames()
    assert "alice" in usernames


def test_undo_rotate_password_rolls_back_credentials_if_apply_fails(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch,
):
    """rotate_user_password already rewrote credentials.toml before
    apply_tt_config_change runs — if apply fails, credentials must go back to
    what they were before this undo attempt, matching _apply_rotate_password_sync's
    own rollback. Otherwise disk and running trusttunnel process disagree
    until someone notices and restarts manually."""
    (tt_paths["CRED_FILE"]).write_text(
        '[[client]]\nusername = "alice"\npassword = "new-pass"\n', encoding="utf-8"
    )

    def _boom(**k):
        raise RuntimeError("restart failed")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", _boom)
    bot_tt._set_pending_undo(context, "rotate_password", {"username": "alice", "old_password": "old-pass"})

    update = allowed_callback_update("undo:go")
    update.callback_query.edit_message_caption = AsyncMock()
    run_async(bot_tt.undo_callback(update, context))

    text = (tt_paths["CRED_FILE"]).read_text(encoding="utf-8")
    assert "new-pass" in text
    assert "old-pass" not in text


def test_undo_delete_user_restores_profile_and_sends_new_link(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch,
):
    """random_prefix=True means the restored user gets a NEW prefix (the old
    one was freed on delete) — the old deeplink is dead, so the admin needs
    the new one. The profile (protocol) must also come back, or a later TOML
    export would silently use defaults instead of what the user actually had."""
    (tt_paths["CRED_FILE"]).write_text('[[client]]\nusername = "bob"\npassword = "b"\n', encoding="utf-8")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")
    monkeypatch.setattr(bot_tt, "generate_deeplink", lambda *a, **k: "tt://?x")
    monkeypatch.setattr(bot_tt, "deeplink_qr_png", lambda *a, **k: b"fake-png")
    bot_tt._set_pending_undo(
        context, "delete_user",
        {"username": "alice", "password": "old-pass", "random_prefix": True, "protocol": "quic"},
    )

    update = allowed_callback_update("undo:go")
    run_async(bot_tt.undo_callback(update, context))

    profile = bot_tt._get_user_profile("alice")
    assert profile.get("protocol") == "quic"
    assert profile.get("random_prefix") is True
    update.callback_query.message.reply_photo.assert_awaited_once()
    caption = update.callback_query.message.reply_photo.call_args.kwargs["caption"]
    assert "prefix on" in caption, "mode_label должен включать состояние prefix, как при создании"


def test_undo_restore_file_writes_back_previous_bytes(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch,
):
    target = tt_paths["TT_DIR"] / "vpn.toml"
    target.write_text("new-content\n", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")
    bot_tt._set_pending_undo(
        context, "restore_file",
        {"filename": "vpn.toml", "data": b"old-content\n", "mode": None},
    )

    update = allowed_callback_update("undo:go")
    run_async(bot_tt.undo_callback(update, context))

    assert target.read_text(encoding="utf-8") == "old-content\n"
