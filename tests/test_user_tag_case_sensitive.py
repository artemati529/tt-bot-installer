"""Имена пользователей различают регистр (USERNAME_RE, проверка дубля при
добавлении), а тег «# user: <name>» сравнивался с re.IGNORECASE: удаление
bob снимало и allow-правило пользователя Bob."""

# Тег пишется строкой ПЕРЕД блоком (см. _tag_prefix_rule_with_username).
RULES = (
    '# user: Bob\n[[rule]]\nclient_random_prefix = "aa11"\naction = "allow"\n\n'
    '# user: bob\n[[rule]]\nclient_random_prefix = "bb22"\naction = "allow"\n'
)


def test_removing_bob_keeps_rule_of_Bob(bot_tt, tt_paths):
    tt_paths["RULES_FILE"].write_text(RULES, encoding="utf-8")

    removed = bot_tt._remove_prefix_rules_for_user([], "bob")

    text = tt_paths["RULES_FILE"].read_text(encoding="utf-8")
    assert removed == 1
    assert "aa11" in text and "# user: Bob" in text
    assert "bb22" not in text


def test_tag_keyword_itself_is_case_insensitive(bot_tt, tt_paths):
    tt_paths["RULES_FILE"].write_text(
        '# USER: carol\n[[rule]]\nclient_random_prefix = "cc33"\naction = "allow"\n', encoding="utf-8"
    )

    assert bot_tt._remove_prefix_rules_for_user([], "carol") == 1
