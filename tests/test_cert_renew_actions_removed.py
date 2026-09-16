"""certbot.timer уже автопродлевает сертификат сам — ручные "Renew TT" и
"Обновить" на карточке сертификата были лишними действиями. Кнопки убраны,
вместе с ними — весь мёртвый код под них."""


def test_cert_card_has_no_renew_or_refresh_buttons(bot_tt):
    kb = bot_tt.cert_card_inline_kb()
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert not any(d.startswith("certupd:") for d in datas)
    assert "certr" not in datas
    assert "certlog:20" in datas


def test_cert_log_back_button_goes_to_nav_cert(bot_tt, allowed_callback_update, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "get_certbot_log_tail", lambda lines: "cert log")
    update = allowed_callback_update("certlog:20")

    run_async(bot_tt.cert_log_callback(update, None))

    kb = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert datas[-1] == "nav:cert"


def test_cert_renew_flow_is_removed(bot_tt):
    removed = ("cert_update_callback", "cert_refresh_callback", "_renew_cert_sync", "_cert_renew_task")
    for name in removed:
        assert not hasattr(bot_tt, name), f"{name} must stay removed"

    assert not any(r.name in ("cert_update_callback", "cert_refresh_callback") for r in bot_tt.CALLBACK_ROUTES)
