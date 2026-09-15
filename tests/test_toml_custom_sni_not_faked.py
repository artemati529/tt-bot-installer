"""custom_sni = hostname был no-op (SNI и так по умолчанию = hostname);
держим пустым для паритета с deeplink."""


def test_build_client_style_toml_leaves_custom_sni_empty(bot_tt):
    base = '[endpoint]\nhostname = "vpn.example.com"\naddresses = ["vpn.example.com:443"]\nusername = "alice"\npassword = "secret"\n'

    text = bot_tt._build_client_style_toml(
        base, protocol="h2", random_prefix=False, dns_upstreams=[]
    )

    import tomlkit

    doc = tomlkit.parse(text)
    assert doc["endpoint"]["custom_sni"] == ""
