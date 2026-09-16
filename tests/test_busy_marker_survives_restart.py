"""BUSY_INFO/CRED_LOCK are pure in-memory — if the bot process itself is
killed/restarted mid-OS-upgrade or mid-TT-upgrade, a fresh process starts
with no memory that a long external operation (apt/systemctl) might still
be running, and would happily let the admin start a second one. A marker
file on disk can't prevent that race, but it does let the next startup at
least warn instead of staying silent."""


def test_busy_set_writes_marker_file(bot_tt, tt_paths):
    bot_tt.busy_set("обновление ОС")

    assert bot_tt.BUSY_MARKER_FILE.read_text(encoding="utf-8") == "обновление ОС"


def test_busy_clear_removes_marker_file(bot_tt, tt_paths):
    bot_tt.busy_set("обновление ОС")
    bot_tt.busy_clear()

    assert not bot_tt.BUSY_MARKER_FILE.exists()


def test_consume_stale_busy_marker_returns_and_clears_it(bot_tt, tt_paths):
    bot_tt.BUSY_MARKER_FILE.write_text("обновление TrustTunnel", encoding="utf-8")

    result = bot_tt._consume_stale_busy_marker()

    assert result == "обновление TrustTunnel"
    assert not bot_tt.BUSY_MARKER_FILE.exists()


def test_consume_stale_busy_marker_returns_none_when_absent(bot_tt, tt_paths):
    assert bot_tt._consume_stale_busy_marker() is None
