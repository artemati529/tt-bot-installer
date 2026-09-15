"""add_user_and_make_link пишет credentials.toml до вызова generate_deeplink
(бинарник) — если бинарник падает/таймаутится, credentials.toml должен
атомарно откатиться к old_text, иначе юзер оставался бы в credentials без
возможности повторного добавления ("Пользователь уже существует")."""

import pytest


def test_add_user_rolls_back_credentials_on_deeplink_failure(bot_tt, tt_paths, monkeypatch):
    """generate_deeplink падает → credentials.toml возвращается в исходное состояние."""
    creds_file = tt_paths["CRED_FILE"]
    creds_file.write_text('[endpoint]\nhostname = "x"\n', encoding="utf-8")
    rules_file = tt_paths["RULES_FILE"]
    assert not rules_file.exists()

    def boom_deeplink(*a, **k):
        raise RuntimeError("trusttunnel_endpoint: timeout")

    monkeypatch.setattr(bot_tt, "generate_deeplink", boom_deeplink)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: None)

    with pytest.raises(RuntimeError, match="timeout"):
        bot_tt.add_user_and_make_link("newuser", "secretpass", random_prefix=False)

    assert creds_file.read_text(encoding="utf-8") == '[endpoint]\nhostname = "x"\n'
    assert not rules_file.exists()


def test_add_user_rollback_does_not_create_rules(bot_tt, tt_paths, monkeypatch):
    """Даже если rules.toml уже существует, rollback не должен его менять."""
    creds_file = tt_paths["CRED_FILE"]
    rules_file = tt_paths["RULES_FILE"]
    creds_file.write_text('[endpoint]\nhostname = "x"\n', encoding="utf-8")
    rules_file.write_text('[[rule]]\nclient_random_prefix = "keep"\naction = "allow"\n', encoding="utf-8")
    original_rules_text = rules_file.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("crash after creds write")

    monkeypatch.setattr(bot_tt, "generate_deeplink", boom)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: None)

    with pytest.raises(RuntimeError):
        bot_tt.add_user_and_make_link("newuser", "pass", random_prefix=False)

    assert creds_file.read_text(encoding="utf-8") == '[endpoint]\nhostname = "x"\n'
    assert rules_file.read_text(encoding="utf-8") == original_rules_text


def test_add_user_succeeds_when_deeplink_works(bot_tt, tt_paths, monkeypatch):
    """После фикса нормальный путь (с генерацией deeplink) не сломался."""
    creds_file = tt_paths["CRED_FILE"]
    creds_file.write_text('[endpoint]\nhostname = "x"\n', encoding="utf-8")

    collected_deeplink = []

    def fake_deeplink(*a, **k):
        collected_deeplink.append("ok")
        return "tt://?test-token"

    monkeypatch.setattr(bot_tt, "generate_deeplink", fake_deeplink)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: None)

    result = bot_tt.add_user_and_make_link("newuser", "secretpass", random_prefix=False)

    assert result == "tt://?test-token"
    assert collected_deeplink == ["ok"]
    assert bot_tt.list_usernames() == ["newuser"]


def test_add_user_random_prefix_rollback(bot_tt, tt_paths, monkeypatch):
    """Если генерация с random_prefix упала после записи credentials — откат."""
    creds_file = tt_paths["CRED_FILE"]
    prefix_file = tt_paths["PREFIX_MAP_FILE"]
    rules_file = tt_paths["RULES_FILE"]

    creds_file.write_text('[endpoint]\nhostname = "x"\n', encoding="utf-8")
    assert not prefix_file.exists()
    assert not rules_file.exists()

    def boom(*a, **k):
        raise RuntimeError("generate failed")

    monkeypatch.setattr(bot_tt, "generate_deeplink", boom)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: None)

    with pytest.raises(RuntimeError):
        bot_tt.add_user_and_make_link(
            "newuser", "pass", random_prefix=True, protocol="h2"
        )

    # credentials откатились
    assert creds_file.read_text(encoding="utf-8") == '[endpoint]\nhostname = "x"\n'
    # префикс-мап и правила не должны появиться
    assert not prefix_file.exists() or prefix_file.read_text(encoding="utf-8").strip() == ""
    assert not rules_file.exists()


def test_add_user_random_prefix_rolls_back_map_and_rules_on_late_failure(
    bot_tt, tt_paths, monkeypatch
):
    """Если apply_tt_config_change падает ПОСЛЕ того как
    _save_prefix_map/_tag_prefix_rule_with_username уже отработали (deeplink
    сгенерирован успешно) — откатываться должны и user_prefix_map.toml/
    rules.toml, не только credentials.toml, иначе останется запись про
    несуществующего пользователя."""
    creds_file = tt_paths["CRED_FILE"]
    prefix_file = tt_paths["PREFIX_MAP_FILE"]
    rules_file = tt_paths["RULES_FILE"]

    creds_file.write_text('[[client]]\nusername = "old"\npassword = "oldpass"\n', encoding="utf-8")

    def fake_generate_deeplink(username, *, generate_new_prefix=False, protocol=None, **kw):
        # Имитируем внешний бинарник: он сам создаёт allow-правило с новым префиксом.
        rules_file.write_text(
            '[[rule]]\nclient_random_prefix = "newpfx"\naction = "allow"\n', encoding="utf-8"
        )
        return "tt://?ok"

    def boom_apply(**kw):
        raise RuntimeError("systemctl restart failed")

    monkeypatch.setattr(bot_tt, "generate_deeplink", fake_generate_deeplink)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", boom_apply)

    with pytest.raises(RuntimeError, match="systemctl restart failed"):
        bot_tt.add_user_and_make_link("newuser", "pass", random_prefix=True, protocol="h2")

    assert bot_tt.list_usernames() == ["old"]
    assert not prefix_file.exists() or "newuser" not in prefix_file.read_text(encoding="utf-8")
    assert "newuser" not in rules_file.read_text(encoding="utf-8")
    assert "newpfx" not in rules_file.read_text(encoding="utf-8")
