"""validate_tt_configs() shelled out to `trusttunnel_endpoint vpn.toml
hosts.toml -v` — but -v/--version is a real trusttunnel_endpoint flag that
prints the version and exits before ever reading the settings files (verified
against endpoint/src/main.rs upstream). The "validation" always succeeded
regardless of what was actually in the files."""


def test_validate_tt_configs_accepts_well_formed_toml(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text('listen_address = "0.0.0.0:443"\n', encoding="utf-8")
    (tt_paths["TT_DIR"] / "hosts.toml").write_text('[[hosts]]\nhostname = "vpn.example.com"\n', encoding="utf-8")

    ok, _msg = bot_tt.validate_tt_configs()

    assert ok is True


def test_validate_tt_configs_rejects_malformed_vpn_toml(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text('listen_address = "0.0.0.0:443\n', encoding="utf-8")  # unclosed quote
    (tt_paths["TT_DIR"] / "hosts.toml").write_text('[[hosts]]\nhostname = "vpn.example.com"\n', encoding="utf-8")

    ok, msg = bot_tt.validate_tt_configs()

    assert ok is False
    assert "vpn.toml" in msg


def test_validate_tt_configs_rejects_malformed_hosts_toml(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text('listen_address = "0.0.0.0:443"\n', encoding="utf-8")
    (tt_paths["TT_DIR"] / "hosts.toml").write_text("[[hosts\n", encoding="utf-8")

    ok, msg = bot_tt.validate_tt_configs()

    assert ok is False
    assert "hosts.toml" in msg


def test_validate_tt_configs_rejects_missing_file(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text('listen_address = "0.0.0.0:443"\n', encoding="utf-8")
    # hosts.toml not created

    ok, _msg = bot_tt.validate_tt_configs()

    assert ok is False
