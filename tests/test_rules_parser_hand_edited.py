"""Парсер блоков rules.toml на файлах, правленных руками:
- комментарий ВНУТРИ [[rule]] обрывал блок — при удалении хвост блока
  прилипал к соседнему правилу (дубль ключа → невалидный TOML, либо
  молча изменённый смысл соседнего правила);
- значения в одинарных кавычках tomlkit видит, а regex — нет: такое
  правило вечно висело «сиротой», которую cleanup не мог удалить;
- validate_tt_configs не проверял rules.toml/credentials.toml, и битый
  файл доходил до restart."""
import pytest
import tomlkit

DENY = '[[rule]]\ncidr = "10.0.0.0/8"\naction = "deny"\n\n'


def test_comment_inside_block_is_removed_with_the_block(bot_tt, tt_paths):
    rules = DENY + (
        '[[rule]]\nclient_random_prefix = "aa11"\n# note\ncidr = "1.2.3.4/32"\naction = "allow"\n'
    )
    tt_paths["RULES_FILE"].write_text(rules, encoding="utf-8")

    assert bot_tt._remove_prefix_rules_by_prefix("aa11") == 1

    text = tt_paths["RULES_FILE"].read_text(encoding="utf-8")
    doc = tomlkit.parse(text)
    assert [dict(r) for r in doc["rule"]] == [{"cidr": "10.0.0.0/8", "action": "deny"}]


def test_trailing_comment_after_block_still_preserved(bot_tt, tt_paths):
    rules = '[[rule]]\nclient_random_prefix = "aa11"\naction = "allow"\n\n# section: misc\n' + DENY
    tt_paths["RULES_FILE"].write_text(rules, encoding="utf-8")

    assert bot_tt._remove_prefix_rules_by_prefix("aa11") == 1

    text = tt_paths["RULES_FILE"].read_text(encoding="utf-8")
    assert "# section: misc" in text
    assert "10.0.0.0/8" in text


def test_single_quoted_rule_is_parsed_and_removable(bot_tt, tt_paths):
    tt_paths["RULES_FILE"].write_text(
        DENY + "[[rule]]\nclient_random_prefix = 'bb22'\naction = 'allow'\n", encoding="utf-8"
    )

    assert bot_tt._parse_rule_block_fields(["client_random_prefix = 'bb22'\n", "action = 'allow'\n"]) == ("allow", "bb22")
    assert bot_tt._remove_prefix_rules_by_prefix("bb22") == 1
    assert "bb22" not in tt_paths["RULES_FILE"].read_text(encoding="utf-8")


def _valid_base(tt_paths):
    d = tt_paths["TT_DIR"]
    (d / "vpn.toml").write_text('listen_address = "0.0.0.0:443"\n', encoding="utf-8")
    (d / "hosts.toml").write_text('[[main_hosts]]\nhostname = "vpn.example.com"\n', encoding="utf-8")
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")


@pytest.mark.parametrize("name", ["rules.toml", "credentials.toml"])
def test_validate_rejects_broken_rules_and_credentials(bot_tt, tt_paths, name):
    _valid_base(tt_paths)
    (tt_paths["TT_DIR"] / name).write_text('[[rule]]\naction = "allow"\naction = "deny"\n', encoding="utf-8")

    ok, msg = bot_tt.validate_tt_configs()

    assert ok is False
    assert name in msg


def test_validate_accepts_missing_rules_file(bot_tt, tt_paths):
    _valid_base(tt_paths)
    assert bot_tt.validate_tt_configs() == (True, "ok")

