"""VPN subflows must reuse the tracked screen and return to VPN."""
from unittest.mock import AsyncMock, MagicMock


def _mock_bot(context):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()


def _button_datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def _button_texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def test_vpn_hub_names_top_export_as_qr(bot_tt):
    kb = bot_tt.vpn_hub_kb()
    datas = _button_datas(kb)
    texts = _button_texts(kb)

    idx = datas.index("vpn:export")
    assert texts[idx] == "📤 QR"
    assert "📤 Экспорт" not in texts


def test_vpn_hub_export_reuses_tracked_screen(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    # force_new deletes the tracked card before sending the next one.
    _mock_bot(context)
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 111
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    update = allowed_callback_update("vpn:export")

    run_async(bot_tt.vpn_hub_callback(update, context))

    context.bot.delete_message.assert_called_once_with(chat_id=111111, message_id=111)
    context.bot.send_message.assert_called_once()


def test_vpn_hub_delete_reuses_tracked_screen(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    _mock_bot(context)
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 111
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])
    update = allowed_callback_update("vpn:del")

    run_async(bot_tt.vpn_hub_callback(update, context))

    context.bot.delete_message.assert_called_once_with(chat_id=111111, message_id=111)
    context.bot.send_message.assert_called_once()


def test_export_pick_back_button_returns_to_vpn_not_home(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])

    run_async(bot_tt.run_export_pick(context.bot, 111111, context=context))

    kb = context.bot.send_message.call_args.kwargs["reply_markup"]
    back_row = kb.inline_keyboard[-1]
    assert back_row[0].callback_data == "nav:vpn"


def test_export_pick_card_is_named_qr(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])

    run_async(bot_tt.run_export_pick(context.bot, 111111, context=context))

    text = context.bot.send_message.call_args.kwargs["text"]
    assert "<b>📤 QR</b>" in text
    assert "Экспорт профиля" not in text


def test_export_protocol_card_is_named_qr(bot_tt, allowed_callback_update, run_async):
    update = allowed_callback_update("exppick:alice")

    run_async(bot_tt.export_pick_callback(update, None))

    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "<b>📤 QR</b>" in text
    assert "Экспорт профиля" not in text


def test_rotate_pick_back_button_returns_to_vpn_not_home(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])

    run_async(bot_tt.run_rotate_pick(context.bot, 111111, context))

    kb = context.bot.send_message.call_args.kwargs["reply_markup"]
    back_row = kb.inline_keyboard[-1]
    assert back_row[0].callback_data == "nav:vpn"


def test_delete_pick_back_button_returns_to_vpn_not_home(bot_tt, context, run_async, monkeypatch):
    _mock_bot(context)
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])

    run_async(bot_tt.run_user_delete_list(context.bot, 111111, context=context))

    kb = context.bot.send_message.call_args.kwargs["reply_markup"]
    back_row = kb.inline_keyboard[-1]
    assert back_row[0].callback_data == "nav:vpn"
