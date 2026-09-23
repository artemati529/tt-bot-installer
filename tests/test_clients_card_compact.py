"""Clients card should stay compact on mobile."""


def _datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_clients_card_uses_compact_rows_without_session_counts(bot_tt, monkeypatch):
    monkeypatch.setattr(
        bot_tt,
        "_fetch_metrics_clients",
        lambda: [
            {
                "username": "bob",
                "sessions": 2,
                "inbound": 12 * 1024**2,
                "outbound": 34 * 1024**2,
            },
            {
                "username": "alice",
                "sessions": 1,
                "inbound": 56 * 1024**2,
                "outbound": 78 * 1024**2,
            },
        ],
    )

    text, total_pages = bot_tt.clients_card_html(0)

    assert total_pages == 1
    assert "сесс" not in text
    assert "📈 +" not in text
    assert "1. 🟢 <b>bob</b>\n    📥 <code>12.0 MiB</code> · 📤 <code>34.0 MiB</code>" in text
    assert "\n\n2. 🟢" not in text
    assert "\n2. 🟢 <b>alice</b>\n    📥 <code>56.0 MiB</code> · 📤 <code>78.0 MiB</code>" in text


def test_clients_card_refresh_and_back_share_bottom_row(bot_tt):
    rows = bot_tt.clients_inline_kb(0, 1).inline_keyboard

    assert [[btn.callback_data for btn in row] for row in rows] == [["ss:0", "nav:home"]]
    assert [btn.text for btn in rows[0]] == ["🔄 Обновить", "⬅️ Назад"]


def test_clients_card_pagination_keeps_compact_bottom_row(bot_tt):
    rows = bot_tt.clients_inline_kb(1, 3).inline_keyboard

    assert [[btn.callback_data for btn in row] for row in rows] == [
        ["ss:0", "ss:2"],
        ["ss:1", "nav:home"],
    ]
