"""Rule repair must create and tag missing prefix rules."""
from unittest.mock import MagicMock


def _write_credentials(cred_file, usernames):
    blocks = [f'[[client]]\nusername = "{u}"\npassword = "x"\n' for u in usernames]
    cred_file.write_text("\n".join(blocks), encoding="utf-8")


def test_repair_actually_creates_and_tags_the_missing_rule(bot_tt, tt_paths, monkeypatch):
    _write_credentials(tt_paths["CRED_FILE"], ["charlie"])
    tt_paths["RULES_FILE"].write_text("", encoding="utf-8")
    bot_tt._save_prefix_map({"charlie": "deadbeef"})
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", MagicMock(return_value="restart"))

    fixed, errors = bot_tt.repair_missing_rules_sync()

    assert errors == []
    assert fixed == ["charlie"]
    assert "deadbeef" in bot_tt._extract_allow_prefixes()
    rules_text = tt_paths["RULES_FILE"].read_text(encoding="utf-8")
    assert "# user: charlie" in rules_text
