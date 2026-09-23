"""Пароль может содержать кавычку (add/rotate запрещают только \\n\\r\\t).
tomlkit экранирует её как \\", а маска "[^"]*" обрывалась на ней — хвост
пароля уходил в чат через /diff открытым текстом."""
import tomlkit


def _creds_text(password: str) -> str:
    doc = tomlkit.document()
    aot = tomlkit.aot()
    client = tomlkit.table()
    client["username"] = "alice"
    client["password"] = password
    aot.append(client)
    doc["client"] = aot
    return tomlkit.dumps(doc)


def test_mask_hides_tail_after_escaped_quote(bot_tt):
    masked = bot_tt._mask_passwords(_creds_text('ab"SECRETTAIL'))
    assert "SECRETTAIL" not in masked
    assert 'password = "•••"\n' in masked


def test_mask_hides_password_ending_with_backslash(bot_tt):
    masked = bot_tt._mask_passwords(_creds_text("abc\\") + 'username2 = "keep-me"\n')
    assert "abc" not in masked
    assert "keep-me" in masked


def test_mask_hides_multiline_basic_string(bot_tt):
    text = 'password = """line1\nSECRET2"""\nusername = "alice"\n'
    masked = bot_tt._mask_passwords(text)
    assert "SECRET2" not in masked
    assert 'username = "alice"' in masked


def test_mask_hides_multiline_literal_string(bot_tt):
    text = "password = '''line1\nSECRET3'''\nusername = \"alice\"\n"
    masked = bot_tt._mask_passwords(text)
    assert "SECRET3" not in masked
    assert 'username = "alice"' in masked


def test_diff_does_not_leak_escaped_quote_password(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    creds = tt_paths["CRED_FILE"]
    creds.write_text(_creds_text('old"OLDTAIL'), encoding="utf-8")
    bot_tt.create_configs_backup()
    creds.write_text(_creds_text('new"NEWTAIL'), encoding="utf-8")

    diff_text = bot_tt._diff_against_latest_backup()

    assert "OLDTAIL" not in diff_text
    assert "NEWTAIL" not in diff_text
