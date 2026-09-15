"""VPN_MONITOR_PORT не должен быть жёстко 443 для всех — читаем реальный
listen_address из vpn.toml, если VPN_MONITOR_PORT явно не задан в .env."""


def test_detects_port_from_listen_address(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text('listen_address = "0.0.0.0:8443"\n', encoding="utf-8")
    assert bot_tt._detect_tt_listen_port() == 8443


def test_returns_none_when_vpn_toml_missing(bot_tt, tt_paths):
    assert bot_tt._detect_tt_listen_port() is None


def test_returns_none_when_listen_address_missing(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text('credentials_file = "credentials.toml"\n', encoding="utf-8")
    assert bot_tt._detect_tt_listen_port() is None


def test_returns_none_on_malformed_toml(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("not = [valid toml", encoding="utf-8")
    assert bot_tt._detect_tt_listen_port() is None
