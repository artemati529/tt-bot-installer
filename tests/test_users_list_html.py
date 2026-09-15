"""User-list rendering must return the sorted usernames."""


def _write_credentials(cred_file, usernames):
    blocks = [f'[[client]]\nusername = "{u}"\npassword = "x"\n' for u in usernames]
    cred_file.write_text("\n".join(blocks), encoding="utf-8")


def _datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def _texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def test_build_users_list_html_returns_sorted_usernames(bot_tt, tt_paths):
    _write_credentials(tt_paths["CRED_FILE"], ["charlie", "alice", "bob"])

    html_text, total_pages, users = bot_tt.build_users_list_html(0)

    assert users == ["alice", "bob", "charlie"]
    assert total_pages == 1
    assert "Всего: <code>3</code>" in html_text


def test_build_users_list_html_filters_online_users(bot_tt, tt_paths, monkeypatch):
    _write_credentials(tt_paths["CRED_FILE"], ["alice", "bob", "charlie"])
    monkeypatch.setattr(
        bot_tt,
        "_fetch_metrics_clients",
        lambda: [
            {"username": "bob", "sessions": 2},
            {"username": "charlie", "sessions": 0},
        ],
    )

    html_text, total_pages, users = bot_tt.build_users_list_html(0, filter_mode="online")

    assert users == ["bob"]
    assert total_pages == 1
    assert "Фильтр: <code>Онлайн</code>" in html_text
    assert "Онлайн: <code>1</code>" in html_text


def test_build_users_list_html_filters_offline_users(bot_tt, tt_paths, monkeypatch):
    _write_credentials(tt_paths["CRED_FILE"], ["alice", "bob", "charlie"])
    monkeypatch.setattr(
        bot_tt,
        "_fetch_metrics_clients",
        lambda: [
            {"username": "bob", "sessions": 1},
            {"username": "charlie", "sessions": 0},
        ],
    )

    _, _, users = bot_tt.build_users_list_html(0, filter_mode="offline")

    assert users == ["alice", "charlie"]


def test_users_list_keyboard_has_filters_and_short_user_labels(bot_tt, tt_paths, monkeypatch):
    tt_paths["USER_PROFILES_FILE"].write_text(
        '{"bob": {"protocol": "quic", "random_prefix": true}}',
        encoding="utf-8",
    )
    tt_paths["PREFIX_MAP_FILE"].write_text('[user_prefix]\nbob = "ab12cd"\n', encoding="utf-8")
    monkeypatch.setattr(bot_tt, "_fetch_metrics_clients", lambda: [{"username": "bob", "sessions": 1}])

    kb = bot_tt.users_list_inline_kb(0, 1, ["bob"], filter_mode="online")

    assert {"uf:all", "uf:online", "uf:offline"}.issubset(set(_datas(kb)))
    assert "ul:0" in _datas(kb)
    assert "🟢 bob" in _texts(kb)
    assert not any("ab12cd" in text or "QUIC" in text or "HTTP/2" in text for text in _texts(kb))


def test_users_list_keyboard_uses_compact_bottom_row_without_extra_actions(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "_fetch_metrics_clients", list)

    kb = bot_tt.users_list_inline_kb(0, 1, ["alice"], filter_mode="all")
    rows = kb.inline_keyboard
    datas_by_row = [[btn.callback_data for btn in row] for row in rows]
    texts_by_row = [[btn.text for btn in row] for row in rows]
    flat_datas = [data for row in datas_by_row for data in row]

    assert "vpn:find" not in flat_datas
    assert "rulesync:view" not in flat_datas
    assert datas_by_row[-1] == ["ul:0", "nav:vpn"]
    assert texts_by_row[-1] == ["🔄 Обновить", "⬅️ Назад"]


def test_users_list_keyboard_pagination_keeps_compact_bottom_row(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "_fetch_metrics_clients", list)

    rows = bot_tt.users_list_inline_kb(1, 3, ["alice"], filter_mode="all").inline_keyboard

    assert [[btn.callback_data for btn in row] for row in rows][-2:] == [
        ["ul:0", "ul:2"],
        ["ul:1", "nav:vpn"],
    ]
