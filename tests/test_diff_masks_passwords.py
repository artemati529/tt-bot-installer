"""_diff_against_latest_backup не должен показывать пароли plaintext'ом —
credentials.toml входит в BACKUP_FILES, а diff_command шлёт результат
прямо в Telegram-чат как <pre>. Значение password маскируется одинаково
по обе стороны диффа, само изменение (что пароль сменился) остаётся видно."""


def test_diff_masks_password_value(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    creds = tt_paths["CRED_FILE"]

    creds.write_text('[[client]]\nusername = "alice"\npassword = "old-secret-pw"\n', encoding="utf-8")
    bot_tt.create_configs_backup()

    creds.write_text('[[client]]\nusername = "alice"\npassword = "new-secret-pw"\n', encoding="utf-8")

    diff_text = bot_tt._diff_against_latest_backup()

    assert "old-secret-pw" not in diff_text
    assert "new-secret-pw" not in diff_text
    assert "password" in diff_text


def test_diff_still_shows_that_password_changed(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    creds = tt_paths["CRED_FILE"]

    creds.write_text('[[client]]\nusername = "alice"\npassword = "old-secret-pw"\n', encoding="utf-8")
    bot_tt.create_configs_backup()

    creds.write_text('[[client]]\nusername = "alice"\npassword = "new-secret-pw"\n', encoding="utf-8")

    diff_text = bot_tt._diff_against_latest_backup()

    assert diff_text != "Изменений нет — конфиги совпадают с последним бэкапом."


def test_diff_no_false_change_when_password_unchanged(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    creds = tt_paths["CRED_FILE"]

    creds.write_text('[[client]]\nusername = "alice"\npassword = "same-pw"\n', encoding="utf-8")
    bot_tt.create_configs_backup()

    diff_text = bot_tt._diff_against_latest_backup()

    assert diff_text == "Изменений нет — конфиги совпадают с последним бэкапом."
