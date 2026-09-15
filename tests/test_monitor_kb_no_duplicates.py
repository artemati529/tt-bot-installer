"""Server menu must expose certificate directly instead of a monitoring hub."""


def test_server_hub_has_certificate_instead_of_monitoring(bot_tt):
    kb = bot_tt.server_hub_kb()
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "nav:info" not in callback_datas
    assert "nav:clients" not in callback_datas
    assert "nav:cert" in callback_datas
    assert "nav:monitor" not in callback_datas
    assert "nav:logs" not in callback_datas
    assert "nav:diag" not in callback_datas
    assert "nav:debug" not in callback_datas


def test_home_hub_kb_still_has_info_and_clients(bot_tt):
    kb = bot_tt.hub_inline_kb()
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "nav:info" in callback_datas
    assert "nav:clients" in callback_datas
