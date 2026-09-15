"""The 5-minute log view must show a time-window header."""


def test_5m_header_describes_the_time_window_not_line_count(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "_fetch_logs_raw", lambda *a, **k: (0, "some ERROR line", ""))

    text, _, _ = bot_tt.build_logs_view(level="5m", lines=50, chunk=0)

    assert "последние 5 минут" in text
    assert "last 50" not in text
