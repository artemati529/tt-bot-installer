"""Protocol keyboard labels and callbacks must stay consistent."""


def test_protocol_kb_rows_labels_and_callbacks(bot_tt):
    rows = bot_tt._protocol_kb_rows(lambda p: f"x:{p}")

    assert [btn.text for row in rows for btn in row] == ["Протокол: HTTP/2", "Протокол: QUIC"]
    assert [btn.callback_data for row in rows for btn in row] == ["x:h2", "x:quic"]
