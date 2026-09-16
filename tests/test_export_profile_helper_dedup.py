"""_load_export_profile replaces the identical protocol+random_prefix
loading block duplicated in user_action_toml_callback/user_action_all_callback."""


def test_load_export_profile_returns_protocol_and_random_prefix(bot_tt, tt_paths, run_async):
    tt_paths["USER_PROFILES_FILE"].write_text(
        '{"alice": {"protocol": "quic", "random_prefix": true}}', encoding="utf-8"
    )

    protocol, random_prefix = run_async(bot_tt._load_export_profile("alice"))

    assert protocol == "quic"
    assert random_prefix is True


def test_load_export_profile_defaults_for_unknown_user(bot_tt, tt_paths, run_async):
    tt_paths["USER_PROFILES_FILE"].write_text("{}", encoding="utf-8")

    protocol, random_prefix = run_async(bot_tt._load_export_profile("nobody"))

    assert protocol == "h2"
    assert random_prefix is False
