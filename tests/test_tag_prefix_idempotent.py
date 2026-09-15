"""Prefix rule tagging must be idempotent."""


def test_retagging_the_same_user_is_idempotent(bot_tt, tt_paths):
    tt_paths["RULES_FILE"].write_text(
        '[[rule]]\nclient_random_prefix = "deadbeef"\naction = "allow"\n',
        encoding="utf-8",
    )

    first = bot_tt._tag_prefix_rule_with_username("deadbeef", "alice")
    second = bot_tt._tag_prefix_rule_with_username("deadbeef", "alice")

    assert first > 0
    assert second == 0
    text = tt_paths["RULES_FILE"].read_text(encoding="utf-8")
    assert text.count("# user: alice") == 1
