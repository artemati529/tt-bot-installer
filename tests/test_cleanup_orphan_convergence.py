"""Rules cleanup must remove stale map entries and rules in one pass."""


def _write_credentials(cred_file, usernames):
    blocks = [f'[[client]]\nusername = "{u}"\npassword = "x"\n' for u in usernames]
    cred_file.write_text("\n".join(blocks), encoding="utf-8")


def test_orphan_map_entry_and_its_rule_are_removed_in_one_pass(bot_tt, tt_paths):
    # Stale prefix-map entry and matching rule.
    _write_credentials(tt_paths["CRED_FILE"], ["alice"])
    bot_tt._save_prefix_map({"deleted_user": "cafefeed"})
    tt_paths["RULES_FILE"].write_text(
        '[[rule]]\nclient_random_prefix = "cafefeed"\naction = "allow"\n',
        encoding="utf-8",
    )

    removed_rules, removed_map = bot_tt.cleanup_orphan_rules_sync()

    assert removed_map == ["deleted_user"]
    assert removed_rules == ["cafefeed"]
    assert "cafefeed" not in bot_tt._extract_allow_prefixes()
    assert "deleted_user" not in bot_tt._load_prefix_map()
