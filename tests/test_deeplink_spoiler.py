"""Deeplink — это фактически credential (username+password+endpoint).

В чате он должен показываться под спойлером, а не открытым текстом.
Авто-удаление сообщений намеренно НЕ добавляем (по решению владельца).
"""


class _FakeMsg:
    chat_id = 111111
    message_id = 1
    reply_photo = None
    reply_text = None
    delete = None


def _spoiler_body(text):
    """Возвращает содержимое всех <tg-spoiler>...</tg-spoiler> в тексте."""
    import re
    return "".join(re.findall(r"<tg-spoiler>(.*?)</tg-spoiler>", text, flags=re.DOTALL))


def test_quick_link_hides_deeplink_in_spoiler(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    deeplink = "tt://?username=alice&password=s3cr3t-pw&endpoint=vpn.example.com"
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda u: {"protocol": "h2", "random_prefix": False})
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda *a: (deeplink, b"png"))

    from unittest.mock import AsyncMock
    context.bot.send_document = AsyncMock()
    update = allowed_callback_update("ulink:alice")
    update.callback_query.message = _FakeMsg()

    run_async(bot_tt.user_quick_link_callback(update, context))

    sent = context.bot.send_message.await_args
    text = sent.kwargs.get("text") or (sent.args[0] if sent.args else "")
    # пароль не должен торчать открытым текстом
    assert "s3cr3t-pw" in _spoiler_body(text), "пароль должен быть внутри спойлера"
    visible = text.replace("<tg-spoiler>" + _spoiler_body(text) + "</tg-spoiler>", "")
    assert "s3cr3t-pw" not in visible, "пароль виден вне спойлера"
    # сам deeplink (с паролем) тоже под спойлером
    assert "<code>" in text


def test_quick_all_hides_deeplink_in_spoiler(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    deeplink = "tt://?username=alice&password=s3cr3t-pw&endpoint=vpn.example.com"
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    monkeypatch.setattr(bot_tt, "_get_user_profile", lambda u: {"protocol": "h2", "random_prefix": False})
    monkeypatch.setattr(bot_tt, "_export_bundle_sync", lambda *a: (deeplink, b"png"))
    monkeypatch.setattr(bot_tt, "_export_toml_bundle_sync", lambda *a: ("trusttunnel-alice.toml", b"toml"))

    from unittest.mock import AsyncMock
    msg = _FakeMsg()
    msg.reply_photo = AsyncMock()
    msg.delete = AsyncMock()
    context.bot.send_document = AsyncMock()
    update = allowed_callback_update("uall:alice")
    update.callback_query.message = msg

    run_async(bot_tt.user_quick_all_callback(update, context))

    sent = context.bot.send_message.await_args
    text = sent.kwargs.get("text") or (sent.args[0] if sent.args else "")
    assert "s3cr3t-pw" in _spoiler_body(text), "пароль должен быть внутри спойлера"
