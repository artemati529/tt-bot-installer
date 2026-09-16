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
