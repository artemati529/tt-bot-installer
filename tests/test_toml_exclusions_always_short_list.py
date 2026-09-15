"""TOML export must include the compact exclusion list."""


def test_split_ru_exclusions_is_the_agreed_short_list(bot_tt):
    assert bot_tt.SPLIT_RU_EXCLUSIONS == [
        "*.ru",
        "*.su",
        "*.yastatic.net",
        "*.yandex.net",
        "*.yandex.com",
        "*.vk.com",
        "*.vk.me",
        "www.gosuslugi.ru",
        "gu-st.ru",
    ]


def test_build_client_style_toml_always_includes_exclusions(bot_tt):
    base = '[endpoint]\nhostname = "vpn.example.com"\naddresses = ["vpn.example.com:443"]\nusername = "alice"\npassword = "secret"\n'

    text = bot_tt._build_client_style_toml(
        base, protocol="h2", random_prefix=False, dns_upstreams=["https://dns.adguard-dns.com/dns-query"]
    )

    for host in bot_tt.SPLIT_RU_EXCLUSIONS:
        assert host in text, f"{host!r} missing from generated TOML exclusions"


def test_build_client_style_toml_signature_has_no_routing_concept(bot_tt):
    import inspect

    params = inspect.signature(bot_tt._build_client_style_toml).parameters
    assert "routing" not in params
