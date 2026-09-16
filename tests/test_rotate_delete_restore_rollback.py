"""add_user_and_make_link already rolls back credentials.toml if
apply_tt_config_change() fails after the write. rotate/delete/restore-all
didn't — the mutation stayed committed on disk while the bot reported
failure, leaving state that looks reverted but isn't."""


def test_rotate_password_rolls_back_on_apply_failure(bot_tt, tt_paths, monkeypatch):
    creds = tt_paths["CRED_FILE"]
    creds.write_text('[[client]]\nusername = "alice"\npassword = "old-pw"\n', encoding="utf-8")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: (_ for _ in ()).throw(bot_tt.CommandError("boom")))

    try:
        bot_tt._apply_rotate_password_sync("alice", "new-pw")
    except bot_tt.CommandError:
        pass

    assert 'password = "old-pw"' in creds.read_text(encoding="utf-8")
    assert 'password = "new-pw"' not in creds.read_text(encoding="utf-8")


def test_delete_user_rolls_back_all_stores_on_apply_failure(bot_tt, tt_paths, monkeypatch):
    creds = tt_paths["CRED_FILE"]
    creds.write_text(
        '[[client]]\nusername = "alice"\npassword = "pw1"\n'
        '[[client]]\nusername = "bob"\npassword = "pw2"\n',
        encoding="utf-8",
    )
    prefix_file = tt_paths["PREFIX_MAP_FILE"]
    prefix_file.write_text('[user_prefix]\nbob = "pfx-bob"\n', encoding="utf-8")
    rules_file = tt_paths["RULES_FILE"]
    rules_file.write_text('[[rule]]\nclient_random_prefix = "pfx-bob"\naction = "allow"\n', encoding="utf-8")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: (_ for _ in ()).throw(bot_tt.CommandError("boom")))

    try:
        bot_tt._delete_user_and_restart_sync("bob")
    except bot_tt.CommandError:
        pass

    assert "bob" in bot_tt.list_usernames()
    assert "bob" in bot_tt._load_prefix_map()
    assert "pfx-bob" in rules_file.read_text(encoding="utf-8")


def test_restore_multiple_rolls_back_all_files_on_apply_failure(bot_tt, tt_paths, monkeypatch):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    creds = tt_paths["CRED_FILE"]
    rules = tt_paths["RULES_FILE"]
    # Снятый бэкап содержит одно состояние...
    creds.write_text('[[client]]\nusername = "in-tar"\npassword = "in-tar-pw"\n', encoding="utf-8")
    rules.write_text("in-tar-rules\n", encoding="utf-8")
    bot_tt.create_configs_backup()

    # ...а сейчас на диске реально лежит другое — именно оно должно выжить,
    # если восстановление из бэкапа упадёт на apply_tt_config_change.
    creds.write_text('[[client]]\nusername = "on-disk"\npassword = "on-disk-pw"\n', encoding="utf-8")
    rules.write_text("on-disk-rules\n", encoding="utf-8")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: (_ for _ in ()).throw(bot_tt.CommandError("boom")))

    ok, _info = bot_tt.restore_multiple_from_latest_backup(["credentials.toml", "rules.toml"])

    assert ok is False
    assert 'password = "on-disk-pw"' in creds.read_text(encoding="utf-8")
    assert "on-disk-rules" in rules.read_text(encoding="utf-8")
    assert "in-tar-pw" not in creds.read_text(encoding="utf-8")
    assert "in-tar-rules" not in rules.read_text(encoding="utf-8")
