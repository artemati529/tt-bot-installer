"""Monitoring-adjacent cards must return to their direct parent."""


def _datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def _texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def test_logs_back_to_load_and_cert_back_to_server(bot_tt):
    assert "nav:info" in _datas(bot_tt.logs_inline_kb("all", 50, 0, 1))
    assert "nav:server" in _datas(bot_tt.cert_card_inline_kb())


def test_top_level_cards_back_to_home(bot_tt):
    for kb in (
        bot_tt.info_card_inline_kb(),
        bot_tt.clients_inline_kb(0, 1),
    ):
        assert "nav:home" in _datas(kb), f"топ-уровневая карточка ведёт не на главную: {kb}"


def test_info_card_buttons_stay_compact_without_diag_or_debug(bot_tt):
    datas = _datas(bot_tt.info_card_inline_kb())

    assert "infor" in datas
    assert "nav:logs" in datas
    assert "nav:cert" not in datas
    assert "nav:diag" not in datas
    assert "nav:debug" not in datas
    assert not any(data.startswith("dbg:") for data in datas)


def test_info_card_buttons_use_half_width_actions_and_full_width_back(bot_tt):
    rows = bot_tt.info_card_inline_kb().inline_keyboard

    assert [btn.callback_data for btn in rows[0]] == ["infor", "nav:logs"]
    assert [btn.callback_data for btn in rows[1]] == ["nav:home"]


def test_refresh_buttons_use_common_label(bot_tt):
    keyboards = (
        bot_tt.server_card_inline_kb(),
        bot_tt.logs_inline_kb("all", 50, 0, 1),
        bot_tt.rules_sync_inline_kb(),
    )

    for kb in keyboards:
        texts = _texts(kb)
        assert "🔄 Обновить" in texts
        assert "🔄" not in texts
        assert "🔄 Отчёт" not in texts


def test_refresh_back_row_uses_common_labels_and_parent_map(bot_tt):
    row = bot_tt.refresh_back_row("ss:0", "home")

    assert [btn.callback_data for btn in row] == ["ss:0", "nav:home"]
    assert [btn.text for btn in row] == ["🔄 Обновить", "⬅️ Назад"]


def test_certbot_log_uses_common_back_label(bot_tt, allowed_callback_update, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "get_certbot_log_tail", lambda lines: "cert log")
    update = allowed_callback_update("certlog:20")

    run_async(bot_tt.cert_log_callback(update, None))

    kb = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
    assert _datas(kb)[-1] == "nav:cert"
    assert _texts(kb)[-1] == "⬅️ Назад"
