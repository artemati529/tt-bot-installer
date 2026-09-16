"""User detail cards must avoid duplicate QR and TOML buttons."""


def _callback_datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_user_detail_kb_single_qr_and_toml(bot_tt):
    kb = bot_tt.user_detail_inline_kb("alice")
    datas = _callback_datas(kb)

    assert datas.count("uqr:alice") == 1
    assert datas.count("utc:alice") == 1
    assert "ure:alice" not in datas
    assert "tc:alice" not in datas


def test_user_detail_kb_keeps_password_delete_and_back(bot_tt):
    kb = bot_tt.user_detail_inline_kb("alice")
    datas = _callback_datas(kb)

    assert "urot:alice" in datas
    assert "udel:alice" in datas
    assert "nav:users:0" in datas


def test_user_detail_kb_has_link_and_all_actions(bot_tt):
    kb = bot_tt.user_detail_inline_kb("alice")
    datas = _callback_datas(kb)

    assert "ulink:alice" in datas
    assert "uall:alice" in datas


def test_user_quick_link_kb_uses_direct_toml(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda username: ("tt://alice", b"png"))
    update = allowed_callback_update("ulink:alice")

    run_async(bot_tt.user_action_link_callback(update, context))

    context.bot.send_message.assert_awaited_once()
    datas = _callback_datas(context.bot.send_message.await_args.kwargs["reply_markup"])
    assert "utc:alice" in datas
    assert "tc:alice" not in datas


def test_old_ure_utc_handlers_still_registered_patterns(bot_tt):
    """Old chat-history button patterns must stay registered."""
    patterns = {route.pattern for route in bot_tt.CALLBACK_ROUTES}

    assert r"^(uqr:|ure:)" in patterns
    assert r"^utc:" in patterns
    assert r"^ulink:" in patterns
    assert r"^uall:" in patterns


def test_toml_share_kb_returns_home_not_card(bot_tt):
    kb = bot_tt.toml_share_kb("alice")
    datas = _callback_datas(kb)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]

    assert "nav:home" in datas
    assert "udev:alice" not in datas
    assert not any("Карточка" in text for text in texts)
