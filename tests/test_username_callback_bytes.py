"""Лимит callback_data у Telegram — 64 БАЙТА, а длина имени проверялась в
символах. Кириллическое имя из вручную правленного credentials.toml
(30 букв = 60 байт) давало «udev:…» в 65 байт → Telegram отклонял всю
клавиатуру, список пользователей не открывался."""

FITS = "я" * 25       # 50 байт — ровно лимит
TOO_LONG = "я" * 26   # 52 байта


def _datas(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]


def test_users_list_skips_names_over_byte_limit(bot_tt):
    datas = _datas(bot_tt.users_list_inline_kb(0, 1, [FITS, TOO_LONG]))
    assert f"udev:{FITS}" in datas
    assert all(TOO_LONG not in d for d in datas)
    assert all(len(d.encode()) <= 64 for d in datas)


def test_user_detail_and_toml_kb_stay_within_64_bytes(bot_tt):
    hand_edited = "я" * 30  # 60 байт: «ulink:» + имя = 66 > 64
    for kb in (bot_tt.user_detail_inline_kb(hand_edited), bot_tt.toml_share_kb(hand_edited)):
        assert all(len(d.encode()) <= 64 for d in _datas(kb))
    assert f"urot:{FITS}" in _datas(bot_tt.user_detail_inline_kb(FITS))


def test_user_pick_hides_names_over_byte_limit(bot_tt):
    assert bot_tt._classify_user_pick([FITS, TOO_LONG]) == ("ok", [FITS], True)
    assert bot_tt._classify_user_pick([TOO_LONG])[0] == "too_long"


def test_longest_route_prefix_fits_with_max_name(bot_tt):
    name = "a" * bot_tt.MAX_USERNAME_LEN
    assert len(f"expproto:quic:{name}".encode()) <= 64
