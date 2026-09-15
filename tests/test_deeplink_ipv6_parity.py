"""deeplink должен получать has_ipv6=false так же, как .toml (сервер без IPv6)."""
import base64

TAG_HOSTNAME = 0x01
TAG_ADDRESSES = 0x02
TAG_HAS_IPV6 = 0x04
TAG_USERNAME = 0x05
TAG_PASSWORD = 0x06


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(payload: str) -> bytes:
    padded = payload + "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(padded)


def _encode_tlv(tag: int, value: bytes) -> bytes:
    assert tag <= 0x3F and len(value) <= 0x3F, "тесты держат тег/длину в 1 байте варинта"
    return bytes([tag]) + bytes([len(value)]) + value


def _build_deeplink(*, has_ipv6: bool | None) -> str:
    """has_ipv6=None — тег не кладём (дефолт апстрима true)."""
    parts = [
        _encode_tlv(TAG_HOSTNAME, b"vpn.example.com"),
        _encode_tlv(TAG_ADDRESSES, b"1.2.3.4:443"),
        _encode_tlv(TAG_USERNAME, b"alice"),
        _encode_tlv(TAG_PASSWORD, b"secret"),
    ]
    if has_ipv6 is not None:
        parts.append(_encode_tlv(TAG_HAS_IPV6, b"\x01" if has_ipv6 else b"\x00"))
    return "tt://?" + _b64url_encode(b"".join(parts))


def _decode_tlvs(deeplink: str) -> dict[int, bytes]:
    data = _b64url_decode(deeplink.removeprefix("tt://?"))
    out: dict[int, bytes] = {}
    offset = 0
    while offset < len(data):
        tag = data[offset]
        length = data[offset + 1]
        value = data[offset + 2 : offset + 2 + length]
        out[tag] = value
        offset += 2 + length
    return out


def test_varint_roundtrip_boundaries(bot_tt):
    for value in (0, 1, 0x3F, 0x40, 0x3FFF, 0x4000, 0x3FFFFFFF):
        encoded = bot_tt._deeplink_write_varint(value)
        decoded, consumed = bot_tt._deeplink_read_varint(encoded + b"\x00", 0)
        assert decoded == value
        assert consumed == len(encoded)


def test_force_has_ipv6_off_flips_explicit_true(bot_tt):
    deeplink = _build_deeplink(has_ipv6=True)
    patched = bot_tt._deeplink_force_has_ipv6_off(deeplink)
    tlvs = _decode_tlvs(patched)
    assert tlvs[TAG_HAS_IPV6] == b"\x00"
    assert tlvs[TAG_HOSTNAME] == b"vpn.example.com"
    assert tlvs[TAG_USERNAME] == b"alice"
    assert tlvs[TAG_PASSWORD] == b"secret"


def test_force_has_ipv6_off_adds_explicit_false_when_tag_absent(bot_tt):
    deeplink = _build_deeplink(has_ipv6=None)
    assert TAG_HAS_IPV6 not in _decode_tlvs(deeplink)

    patched = bot_tt._deeplink_force_has_ipv6_off(deeplink)
    tlvs = _decode_tlvs(patched)
    assert tlvs[TAG_HAS_IPV6] == b"\x00"


def test_force_has_ipv6_off_noop_if_already_false(bot_tt):
    deeplink = _build_deeplink(has_ipv6=False)
    patched = bot_tt._deeplink_force_has_ipv6_off(deeplink)
    assert _decode_tlvs(patched)[TAG_HAS_IPV6] == b"\x00"


def test_force_has_ipv6_off_ignores_non_deeplink_input(bot_tt):
    assert bot_tt._deeplink_force_has_ipv6_off("not-a-deeplink") == "not-a-deeplink"
    assert bot_tt._deeplink_force_has_ipv6_off("") == ""


def test_force_has_ipv6_off_survives_malformed_payload(bot_tt):
    broken = "tt://?%%%not-base64%%%"
    assert bot_tt._deeplink_force_has_ipv6_off(broken) == broken


def test_generate_deeplink_applies_ipv6_patch(bot_tt, monkeypatch):
    raw = _build_deeplink(has_ipv6=True)

    class FakeProcess:
        stdout = raw + "\n"

    monkeypatch.setattr(bot_tt, "run_process", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(bot_tt, "_client_endpoint_address", lambda addr: "vpn.example.com")

    result = bot_tt.generate_deeplink("alice")
    assert _decode_tlvs(result)[TAG_HAS_IPV6] == b"\x00"
