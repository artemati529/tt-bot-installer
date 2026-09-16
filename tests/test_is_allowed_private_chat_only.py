"""is_allowed сверяет только user_id, не тип чата. Если бот окажется в группе
(добавили случайно, тестировали) и разрешённый юзер напишет там команду —
ответ (статус/логи/карточка сертификата) уйдёт в группу, а не в личку.
_chat_id всегда берёт update.effective_chat.id — то есть отвечает туда,
откуда пришла команда, без привязки к личному чату."""
from unittest.mock import MagicMock


def _update(chat_type: str):
    u = MagicMock()
    u.effective_user = MagicMock(id=111111, username="admin")
    u.effective_chat = MagicMock(id=-987654, type=chat_type)
    return u


def test_allowed_user_from_private_chat_is_allowed(bot_tt):
    assert bot_tt.is_allowed(_update("private")) is True


def test_allowed_user_from_group_chat_is_denied(bot_tt):
    assert bot_tt.is_allowed(_update("group")) is False


def test_allowed_user_from_supergroup_chat_is_denied(bot_tt):
    assert bot_tt.is_allowed(_update("supergroup")) is False


def test_nav_callback_denies_allowed_user_from_group_chat_end_to_end(
    bot_tt, allowed_callback_update, context, run_async
):
    """Тот же разрешённый user_id, но команда пришла из группы — allow_guard
    должен отказать, а не молча ответить в группу."""
    route = next(r for r in bot_tt.CALLBACK_ROUTES if r.name == "nav_callback")
    handler = bot_tt.build_callback_query_handler(route).callback

    update = allowed_callback_update("nav:home", chat_type="group")
    run_async(handler(update, context))

    update.callback_query.answer.assert_awaited_once_with(text="Нет доступа", show_alert=True)
