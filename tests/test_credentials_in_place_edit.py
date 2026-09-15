"""add_user_and_make_link/rotate_user_password/delete_user
все шли через _render_clients_toml — она пересобирает credentials.toml с нуля
из плоского списка {username, password}, не видя исходный tomlkit-документ.
Любая посторонняя таблица (например [endpoint], если файл когда-то правили
руками) или комментарий безвозвратно терялись при первой же записи. Раньше
это проверялось только в rollback-тестах (там просто восстанавливается
old_text байт-в-байт — это не показатель), а успешный путь дыру не ловил.

Фикс: править tomlkit-документ in-place (_load_credentials_doc уже отдаёт doc)
и tomlkit.dumps(doc) вместо пересборки текста.
"""


def test_add_user_success_preserves_foreign_table(bot_tt, tt_paths, monkeypatch):
    creds_file = tt_paths["CRED_FILE"]
    creds_file.write_text(
        '[endpoint]\nhostname = "x"\n\n[[client]]\nusername = "old"\npassword = "oldpass"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_tt, "generate_deeplink", lambda *a, **k: "tt://?test-token")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: None)

    result = bot_tt.add_user_and_make_link("newuser", "secretpass", random_prefix=False)

    assert result == "tt://?test-token"
    text = creds_file.read_text(encoding="utf-8")
    assert "[endpoint]" in text
    assert 'hostname = "x"' in text
    assert bot_tt.list_usernames() == ["old", "newuser"]


def test_rotate_password_preserves_foreign_table(bot_tt, tt_paths):
    creds_file = tt_paths["CRED_FILE"]
    creds_file.write_text(
        '[endpoint]\nhostname = "x"\n\n[[client]]\nusername = "alice"\npassword = "old"\n',
        encoding="utf-8",
    )

    ok = bot_tt.rotate_user_password("alice", "newpass")

    assert ok is True
    text = creds_file.read_text(encoding="utf-8")
    assert "[endpoint]" in text
    assert 'hostname = "x"' in text


def test_delete_user_preserves_foreign_table(bot_tt, tt_paths):
    creds_file = tt_paths["CRED_FILE"]
    creds_file.write_text(
        '[endpoint]\nhostname = "x"\n\n'
        '[[client]]\nusername = "alice"\npassword = "p"\n\n'
        '[[client]]\nusername = "bob"\npassword = "p2"\n',
        encoding="utf-8",
    )

    ok = bot_tt.delete_user("alice")

    assert ok is True
    text = creds_file.read_text(encoding="utf-8")
    assert "[endpoint]" in text
    assert bot_tt.list_usernames() == ["bob"]
