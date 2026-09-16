"""_normalize_protocol replaces 6 copies of the same
`if x not in ("h2", "quic"): x = "h2"` idiom scattered across the file."""


def test_normalize_protocol_passes_through_known_values(bot_tt):
    assert bot_tt._normalize_protocol("h2") == "h2"
    assert bot_tt._normalize_protocol("quic") == "quic"


def test_normalize_protocol_defaults_unknown_to_h2(bot_tt):
    assert bot_tt._normalize_protocol("") == "h2"
    assert bot_tt._normalize_protocol("bogus") == "h2"
    assert bot_tt._normalize_protocol(None) == "h2"
