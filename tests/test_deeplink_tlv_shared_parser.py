"""Разбор TLV deeplink был продублирован в двух функциях, а читатель
QUIC-varint не проверял границы: обрезанный varint молча читался как 0.
_force_has_ipv6_off из битого deeplink без ошибки собирал другой битый
deeplink вместо того, чтобы вернуть вход как есть."""
import base64

import pytest


def _link(raw: bytes) -> str:
    return "tt://?" + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_validate_truncated_varint_is_value_error(bot_tt):
    with pytest.raises(ValueError):
        bot_tt._validate_deeplink(_link(b"\x01\x80"))


def test_force_ipv6_off_returns_input_on_truncated_varint(bot_tt):
    link = _link(b"\x01\x80")
    assert bot_tt._deeplink_force_has_ipv6_off(link) == link


def test_force_ipv6_off_replaces_existing_tag_once(bot_tt):
    link = _link(b"\x01\x01a" + b"\x04\x01\x01" + b"\x05\x01u")
    tags = bot_tt._decode_deeplink_tags(bot_tt._deeplink_force_has_ipv6_off(link))
    assert tags[0x04] == b"\x00"
    assert tags[0x01] == b"a" and tags[0x05] == b"u"
