"""User deletion must remove prefix and tag matches in one pass."""


def test_removes_both_prefix_and_tag_matches_in_a_single_backup(bot_tt, tt_paths):
    tt_paths["RULES_FILE"].write_text(
        '[[rule]]\n'
        'client_random_prefix = "aaaa1111"\n'
        'action = "allow"\n'
        '# user: bob\n'
        '[[rule]]\n'
        'client_random_prefix = "bbbb2222"\n'
        'action = "allow"\n'
        '[[rule]]\n'
        'client_random_prefix = "cccc3333"\n'
        'action = "allow"\n',
        encoding="utf-8",
    )
    backup_dir = tt_paths["TT_DIR"] / "backup" / "rules"

    removed = bot_tt._remove_prefix_rules_for_user(["aaaa1111"], "bob")

    # Prefix and tag matches must be removed together.
    assert removed == 2
    remaining = bot_tt._extract_allow_prefixes()
    assert remaining == ["cccc3333"]
    assert backup_dir.exists()
    assert len(list(backup_dir.glob("rules-*.toml.bak"))) == 1
