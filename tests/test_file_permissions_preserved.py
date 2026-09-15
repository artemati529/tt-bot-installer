"""Атомарная запись/восстановление не должна сбрасывать права
файла на 0600 (режим временного файла NamedTemporaryFile), затирая то, что
реально стояло на vpn.toml/hosts.toml/rules.toml/user_prefix_map.toml.
credentials.toml — исключение, там 0600 всегда осознанно (пароли).
"""


def test_atomic_write_file_preserves_existing_permissions(bot_tt, tt_paths):
    path = tt_paths["RULES_FILE"]
    path.write_text("old content\n", encoding="utf-8")
    path.chmod(0o644)

    bot_tt._atomic_write_file(path, "new content\n")

    assert path.read_text(encoding="utf-8") == "new content\n"
    assert oct(path.stat().st_mode)[-3:] == "644"


def test_atomic_write_file_defaults_when_file_is_new(bot_tt, tt_paths):
    path = tt_paths["RULES_FILE"]
    assert not path.exists()

    bot_tt._atomic_write_file(path, "brand new\n")

    assert path.exists()  # не падает на первом создании файла


def test_restore_preserves_existing_permissions_for_non_credentials_files(bot_tt, tt_paths):
    tt_dir = tt_paths["TT_DIR"]
    (tt_dir / "vpn.toml").write_text("old vpn\n", encoding="utf-8")
    (tt_dir / "vpn.toml").chmod(0o644)
    bot_tt.create_configs_backup()

    (tt_dir / "vpn.toml").write_text("changed after backup\n", encoding="utf-8")
    (tt_dir / "vpn.toml").chmod(0o644)

    ok, msg = bot_tt.restore_file_from_latest_backup("vpn.toml", restart_service=False)

    assert ok, msg
    assert oct((tt_dir / "vpn.toml").stat().st_mode)[-3:] == "644"


def test_restore_still_forces_0600_for_credentials(bot_tt, tt_paths):
    tt_dir = tt_paths["TT_DIR"]
    (tt_dir / "credentials.toml").write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")
    (tt_dir / "credentials.toml").chmod(0o644)
    bot_tt.create_configs_backup()

    ok, msg = bot_tt.restore_file_from_latest_backup("credentials.toml", restart_service=False)

    assert ok, msg
    assert oct((tt_dir / "credentials.toml").stat().st_mode)[-3:] == "600"
