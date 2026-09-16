"""Раскраска кнопок (Bot API 9.4+, PTB 22.7+, style на InlineKeyboardButton):
🔴 danger — confirm-диалоги (Да/Нет) для опасных действий и "Удалить" в
карточке пользователя; 🟢 success — подтверждающие "Да" и все кнопки
"Назад"; хаб-кнопки VPN/Сервер (Новый/Удалить/Restart TT/Обновить ОС/Reboot)
без стиля. Старые клиенты Telegram просто не увидят цвет — не баг."""


def _buttons(kb):
    return [btn for row in kb.inline_keyboard for btn in row]


def _by_data(kb, data):
    for btn in _buttons(kb):
        if btn.callback_data == data:
            return btn
    raise AssertionError(f"no button with callback_data={data!r}")


def test_confirm_kb_yes_is_success_by_default(bot_tt):
    kb = bot_tt.confirm_kb("do:yes", "do:no")
    assert _by_data(kb, "do:yes").style == "success"
    assert _by_data(kb, "do:no").style is None


def test_confirm_kb_yes_is_danger_when_requested(bot_tt):
    kb = bot_tt.confirm_kb("do:yes", "do:no", danger=True)
    assert _by_data(kb, "do:yes").style == "danger"
    assert _by_data(kb, "do:no").style is None


def test_delete_user_confirm_is_danger(bot_tt):
    kb = bot_tt.delete_user_confirm_kb("alice")
    assert _by_data(kb, "del2:alice").style == "danger"


def test_deldo_confirm_is_danger(bot_tt, tt_paths):
    kb = bot_tt.confirm_kb("deldo:alice", "delcancel:alice", danger=True)
    assert _by_data(kb, "deldo:alice").style == "danger"


def test_vpn_hub_buttons_have_no_style(bot_tt):
    kb = bot_tt.vpn_hub_kb()
    assert _by_data(kb, "vpn:del").style is None
    assert _by_data(kb, "vpn:add").style is None
    assert _by_data(kb, "vpn:find").style is None


def test_server_hub_buttons_have_no_style(bot_tt):
    kb = bot_tt.server_hub_kb()
    assert _by_data(kb, "srv:restart").style is None
    assert _by_data(kb, "srv:osupd").style is None
    assert _by_data(kb, "srv:reboot").style is None
    assert _by_data(kb, "srv:backup").style is None


def test_user_quick_delete_button_is_danger(bot_tt):
    kb = bot_tt.user_detail_inline_kb("alice")
    assert _by_data(kb, "udel:alice").style == "danger"


def test_back_buttons_are_success(bot_tt):
    assert bot_tt.card_footer_row("home")[0].style == "success"
    kb = bot_tt.rotate_password_back_kb("udev:alice")
    assert kb.inline_keyboard[0][0].style == "success"
