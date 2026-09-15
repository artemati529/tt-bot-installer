"""New random-prefix rules must survive ambiguous prefix diffs."""
from unittest.mock import MagicMock


def _write_credentials(cred_file, usernames):
    blocks = [f'[[client]]\nusername = "{u}"\npassword = "x"\n' for u in usernames]
    cred_file.write_text("\n".join(blocks), encoding="utf-8")


def _rule_block(prefix: str) -> str:
    return f'[[rule]]\nclient_random_prefix = "{prefix}"\naction = "allow"\n'


def test_ambiguous_new_prefixes_are_not_deleted_by_auto_cleanup(bot_tt, tt_paths, monkeypatch):
    _write_credentials(tt_paths["CRED_FILE"], ["alice"])
    tt_paths["RULES_FILE"].write_text("", encoding="utf-8")

    # Simulate multiple rules created by one prefix generation call.
    def fake_generate_deeplink(username, *, generate_new_prefix=False, client_random_prefix=None, protocol=None):
        existing = bot_tt._extract_allow_prefixes()
        new_text = "\n".join(_rule_block(p) for p in existing) if existing else ""
        new_text += "\n" + _rule_block("aaaa1111") + "\n" + _rule_block("bbbb2222")
        tt_paths["RULES_FILE"].write_text(new_text, encoding="utf-8")
        return "tt://?fake"

    monkeypatch.setattr(bot_tt, "generate_deeplink", fake_generate_deeplink)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", MagicMock(return_value="restart"))

    bot_tt.add_user_and_make_link("bob", "secret", random_prefix=True)

    remaining_prefixes = set(bot_tt._extract_allow_prefixes())
    assert {"aaaa1111", "bbbb2222"} & remaining_prefixes, (
        "the newly generated rule(s) were deleted by auto-cleanup because "
        "they were never recorded in user_prefix_map"
    )

    mapping = bot_tt._load_prefix_map()
    assert "bob" in mapping, "ambiguous diff should still defensively map bob to one of the new prefixes"
