"""User detail text must include profile data without routing state."""


def test_render_user_detail_text_includes_prefix_and_protocol(bot_tt, tt_paths):
    bot_tt._save_prefix_map({"alice": "deadbeef"})
    bot_tt._set_user_profile("alice", protocol="quic", random_prefix=True)

    text = bot_tt._render_user_detail_text("alice")

    assert "alice" in text
    assert "deadbeef" in text
    assert "QUIC" in text
    assert "routing" not in text.lower()
