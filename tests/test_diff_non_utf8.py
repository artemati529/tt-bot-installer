"""/diff молча не отвечал, если живой файл или его копия в бэкапе содержали
не-UTF-8 байты: UnicodeDecodeError не ловился ни в _diff_against_latest_backup,
ни в diff_command."""


def _prepare(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")


def test_diff_survives_non_utf8_live_file(bot_tt, tt_paths):
    _prepare(bot_tt, tt_paths)
    bot_tt.create_configs_backup()
    tt_paths["CRED_FILE"].write_bytes(b'[[client]]\nusername = "a"\npassword = "\xff"\n')

    text = bot_tt._diff_against_latest_backup()

    assert "credentials.toml" in text


def test_diff_survives_non_utf8_backup_copy(bot_tt, tt_paths):
    _prepare(bot_tt, tt_paths)
    tt_paths["RULES_FILE"].write_bytes(b"# \xfe legacy\n")
    bot_tt.create_configs_backup()
    tt_paths["RULES_FILE"].write_text("# fixed\n", encoding="utf-8")

    text = bot_tt._diff_against_latest_backup()

    assert "rules.toml" in text
