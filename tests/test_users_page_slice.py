"""Срез страницы списка пользователей был продублирован в трёх хендлерах."""


def test_page_slice_clamps_and_slices(bot_tt):
    per = bot_tt.USERS_PER_PAGE
    users = [f"u{i}" for i in range(per * 2 + 1)]
    assert bot_tt._users_page_slice(users, 0, 3) == (0, users[:per])
    assert bot_tt._users_page_slice(users, 2, 3) == (2, users[2 * per :])
    assert bot_tt._users_page_slice(users, 9, 3) == (2, users[2 * per :])
    assert bot_tt._users_page_slice(users, -1, 3) == (0, users[:per])
