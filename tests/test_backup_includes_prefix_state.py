"""Бэкап брал credentials.toml и rules.toml, но не user_prefix_map.toml и
user_profiles.json: после «Восстановить всё» правила восстановленных
пользователей оказывались сиротами (нет записи в карте) и авточистка
удаляла их при ближайшем add/delete, а экспорт шёл без префикса."""


def _seed(tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    tt_paths["CRED_FILE"].write_text(
        '[[client]]\nusername = "alice"\npassword = "pw1"\n[[client]]\nusername = "x"\npassword = "pw2"\n',
        encoding="utf-8",
    )
    tt_paths["RULES_FILE"].write_text(
        '# user: x\n[[rule]]\nclient_random_prefix = "aa11"\naction = "allow"\n', encoding="utf-8"
    )
    tt_paths["PREFIX_MAP_FILE"].write_text('[user_prefix]\nx = "aa11"\n', encoding="utf-8")
    tt_paths["USER_PROFILES_FILE"].write_text('{"x": {"random_prefix": true, "protocol": "h2"}}', encoding="utf-8")


def test_backup_contains_prefix_map_and_profiles(bot_tt, tt_paths):
    _seed(tt_paths)
    _path, included = bot_tt.create_configs_backup()
    assert "user_prefix_map.toml" in included
    assert "user_profiles.json" in included


def test_restore_all_keeps_restored_users_rules_alive(bot_tt, tt_paths, monkeypatch):
    _seed(tt_paths)
    bot_tt.create_configs_backup()
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: "restart")

    # Пользователь x удалён после бэкапа — вместе с картой и профилем.
    bot_tt._delete_user_and_restart_sync("x")
    assert "aa11" not in tt_paths["RULES_FILE"].read_text(encoding="utf-8")

    ok, _ = bot_tt.restore_multiple_from_latest_backup(bot_tt.list_files_in_latest_backup())
    assert ok

    assert bot_tt._load_prefix_map() == {"x": "aa11"}
    assert bot_tt._get_user_profile("x").get("random_prefix") is True
    removed_rules, _ = bot_tt._auto_cleanup_rules_orphans()
    assert removed_rules == []
    assert "aa11" in tt_paths["RULES_FILE"].read_text(encoding="utf-8")
