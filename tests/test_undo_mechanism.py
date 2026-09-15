"""Generic pending-undo store: один слот, TTL, забирается один раз."""


def test_set_and_pop_returns_payload(bot_tt, context):
    bot_tt._set_pending_undo(context, "test_kind", {"a": 1})
    info = bot_tt._pop_pending_undo(context)
    assert info == {"kind": "test_kind", "payload": {"a": 1}}


def test_pop_is_one_shot(bot_tt, context):
    bot_tt._set_pending_undo(context, "test_kind", {"a": 1})
    bot_tt._pop_pending_undo(context)
    assert bot_tt._pop_pending_undo(context) is None


def test_pop_without_set_returns_none(bot_tt, context):
    assert bot_tt._pop_pending_undo(context) is None


def test_pop_after_ttl_returns_none(bot_tt, context, monkeypatch):
    bot_tt._set_pending_undo(context, "test_kind", {"a": 1})
    monkeypatch.setattr(bot_tt, "monotonic", lambda: 10**9)
    assert bot_tt._pop_pending_undo(context) is None


def test_set_overwrites_previous_pending_undo(bot_tt, context):
    bot_tt._set_pending_undo(context, "kind1", {"a": 1})
    bot_tt._set_pending_undo(context, "kind2", {"b": 2})
    info = bot_tt._pop_pending_undo(context)
    assert info == {"kind": "kind2", "payload": {"b": 2}}
