"""Валидация перед выдачей deeplink/toml пользователю — регрессионный щит
для has_ipv6/обязательных полей (см. test_deeplink_ipv6_parity.py)."""
import base64


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + bytes([len(value)]) + value


def _deeplink(*, hostname=b"h", addresses=b"1.2.3.4:443", username=b"u", password=b"p", has_ipv6=b"\x00"):
    parts = []
    if hostname is not None:
        parts.append(_tlv(0x01, hostname))
    if addresses is not None:
        parts.append(_tlv(0x02, addresses))
    if username is not None:
        parts.append(_tlv(0x05, username))
    if password is not None:
        parts.append(_tlv(0x06, password))
    if has_ipv6 is not None:
        parts.append(_tlv(0x04, has_ipv6))
    payload = base64.urlsafe_b64encode(b"".join(parts)).rstrip(b"=").decode("ascii")
    return f"tt://?{payload}"


def test_validate_deeplink_accepts_well_formed(bot_tt):
    bot_tt._validate_deeplink(_deeplink())


def test_validate_deeplink_rejects_missing_username(bot_tt):
    import pytest

    with pytest.raises(ValueError):
        bot_tt._validate_deeplink(_deeplink(username=None))


def test_validate_deeplink_rejects_has_ipv6_true(bot_tt):
    import pytest

    with pytest.raises(ValueError):
        bot_tt._validate_deeplink(_deeplink(has_ipv6=b"\x01"))


def test_validate_deeplink_rejects_has_ipv6_absent(bot_tt):
    import pytest

    with pytest.raises(ValueError):
        bot_tt._validate_deeplink(_deeplink(has_ipv6=None))


def test_validate_client_toml_accepts_well_formed(bot_tt):
    text = (
        "[endpoint]\n"
        'hostname = "vpn.example.com"\n'
        'username = "alice"\n'
        'password = "secret"\n'
        "has_ipv6 = false\n"
    )
    bot_tt._validate_client_toml(text)


def test_validate_client_toml_rejects_missing_password(bot_tt):
    import pytest

    text = (
        "[endpoint]\n"
        'hostname = "vpn.example.com"\n'
        'username = "alice"\n'
        "has_ipv6 = false\n"
    )
    with pytest.raises(ValueError):
        bot_tt._validate_client_toml(text)


def test_validate_client_toml_rejects_has_ipv6_true(bot_tt):
    import pytest

    text = (
        "[endpoint]\n"
        'hostname = "vpn.example.com"\n'
        'username = "alice"\n'
        'password = "secret"\n'
        "has_ipv6 = true\n"
    )
    with pytest.raises(ValueError):
        bot_tt._validate_client_toml(text)


def test_validate_client_toml_rejects_missing_endpoint_section(bot_tt):
    import pytest

    with pytest.raises(ValueError):
        bot_tt._validate_client_toml("loglevel = \"info\"\n")


def test_generate_deeplink_output_passes_validation(bot_tt, monkeypatch):
    raw = _deeplink(has_ipv6=b"\x01")

    class FakeProcess:
        stdout = raw + "\n"

    monkeypatch.setattr(bot_tt, "run_process", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(bot_tt, "_client_endpoint_address", lambda addr: "h")

    result = bot_tt.generate_deeplink("alice")
    bot_tt._validate_deeplink(result)


def test_build_client_style_toml_output_passes_validation(bot_tt):
    base = '[endpoint]\nhostname = "vpn.example.com"\naddresses = ["vpn.example.com:443"]\nusername = "alice"\npassword = "secret"\n'
    text = bot_tt._build_client_style_toml(base, protocol="h2", random_prefix=False, dns_upstreams=[])
    bot_tt._validate_client_toml(text)
