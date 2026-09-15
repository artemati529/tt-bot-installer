"""Подпись DNS в TOML-экспорте не должна врать для HTTP/2 — показывать
"Google + Cloudflare", хотя _protocol_dns_values реально прописывает
AdGuard независимо от протокола. Подпись должна отражать то, что реально
уходит в конфиг, а не выдуманный текст."""


def test_protocol_dns_label_matches_actual_dns_values(bot_tt):
    for protocol in ("h2", "quic"):
        values = bot_tt._protocol_dns_values(protocol)
        label = bot_tt._protocol_dns_label(protocol)

        assert all("adguard-dns.com" in v for v in values), values
        assert "adguard" in label.lower(), label
        assert "google" not in label.lower(), label
        assert "cloudflare" not in label.lower(), label
