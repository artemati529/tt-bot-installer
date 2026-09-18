"""_aggregate_sessions_from_metrics and _active_usernames_from_metrics
independently parsed the same metrics-item shape and had already drifted:
one crashed on a malformed "sessions" value, the other defaulted to 0.
Both now go through one shared, guarded parser."""


def test_aggregate_sessions_does_not_crash_on_malformed_sessions_value(bot_tt):
    items = [{"username": "alice", "sessions": "not-a-number"}]

    cnt, _labels = bot_tt._aggregate_sessions_from_metrics(items)

    assert cnt["u:alice"] == 0


def test_active_usernames_still_defaults_malformed_sessions_to_zero(bot_tt):
    items = [{"username": "alice", "sessions": "not-a-number"}]

    assert bot_tt._active_usernames_from_metrics(items) == set()


def test_aggregate_sessions_does_not_crash_on_malformed_traffic_values(bot_tt):
    """inbound/outbound went through a bare int(...) with no guard, unlike
    sessions right above it in the same function — one bad value from the
    metrics endpoint broke the whole clients card, not just that one row."""
    items = [{"username": "alice", "sessions": 1, "inbound": "not-a-number", "outbound": None}]

    cnt, labels = bot_tt._aggregate_sessions_from_metrics(items)

    assert cnt["u:alice"] == 1
    assert "alice" in labels["u:alice"]
