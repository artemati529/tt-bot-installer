"""nav_footer_row и card_footer_row — два словаря
parent→back с почти одинаковым содержимым, но реальным конфликтом на ключе
"server": nav_footer_row["server"] значил "я и есть хаб Сервера" (back →
nav:home), а card_footer_row["server"] значил "мой родитель — хаб Сервера"
(back → nav:server). Раньше это работало только потому, что использовались
раздельно; при объединении в один словарь ключ "server" пришлось бы развести
через card_footer_row("home") на хабе — тест закрепляет, что оба хаба
(vpn/server) по-прежнему ведут "Назад" на nav:home.
"""


def test_vpn_hub_back_button_goes_home(bot_tt):
    kb = bot_tt.vpn_hub_kb()
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "nav:home" in callback_datas


def test_server_hub_back_button_goes_home_not_to_itself(bot_tt):
    kb = bot_tt.server_hub_kb()
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "nav:home" in callback_datas
    assert "nav:server" not in callback_datas


def test_users_list_back_button_goes_to_vpn_hub(bot_tt, tt_paths):
    (tt_paths["CRED_FILE"]).write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")
    _, total_pages, users = bot_tt.build_users_list_html(0, filter_mode="all")
    kb = bot_tt.users_list_inline_kb(0, total_pages, users[:1], filter_mode="all")
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "nav:vpn" in callback_datas


def test_user_pick_back_button_goes_to_vpn_hub(bot_tt, context, run_async, monkeypatch):
    # make_user_inline убран — три пикера (rotate/export/
    # delete) теперь строят клавиатуру сами через run_user_pick + card_footer_row.
    from unittest.mock import AsyncMock, MagicMock

    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    monkeypatch.setattr(bot_tt, "list_usernames", lambda: ["alice"])

    run_async(bot_tt.run_export_pick(context.bot, 111111, context=context))

    kb = context.bot.send_message.call_args.kwargs["reply_markup"]
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "nav:vpn" in callback_datas
