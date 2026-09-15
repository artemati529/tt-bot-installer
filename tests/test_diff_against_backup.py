"""/diff сравнивает живые конфиги с latest-configs.tar.gz — тем же единственным
недатированным бэкапом, который уже использует restore. Ничего нового в
бэкап-механику не добавляется."""


def test_no_backup_yet(bot_tt, tt_paths):
    assert "нет" in bot_tt._diff_against_latest_backup().lower()


def test_no_changes_when_identical(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = 1\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    result = bot_tt._diff_against_latest_backup()
    assert "изменени" in result.lower()
    assert "---" not in result


def test_shows_diff_for_changed_file(bot_tt, tt_paths):
    vpn = tt_paths["TT_DIR"] / "vpn.toml"
    vpn.write_text("a = 1\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    vpn.write_text("a = 2\n", encoding="utf-8")

    result = bot_tt._diff_against_latest_backup()
    assert "vpn.toml" in result
    assert "-a = 1" in result
    assert "+a = 2" in result


def test_only_changed_files_are_shown(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = 1\n", encoding="utf-8")
    (tt_paths["TT_DIR"] / "hosts.toml").write_text("h = 1\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = 2\n", encoding="utf-8")

    result = bot_tt._diff_against_latest_backup()
    assert "vpn.toml" in result
    assert "hosts.toml" not in result


def test_file_added_since_backup(bot_tt, tt_paths):
    bot_tt.create_configs_backup()  # ничего ещё нет
    (tt_paths["TT_DIR"] / "rules.toml").write_text("[[rule]]\n", encoding="utf-8")

    result = bot_tt._diff_against_latest_backup()
    assert "rules.toml" in result
    assert "+[[rule]]" in result


def test_corrupted_backup_does_not_raise(bot_tt, tt_paths):
    backup_dir = tt_paths["TT_DIR"] / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "latest-configs.tar.gz").write_bytes(b"not a tarball")

    result = bot_tt._diff_against_latest_backup()
    assert isinstance(result, str)
    assert result
