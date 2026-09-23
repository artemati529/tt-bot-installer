"""Ожидание нового пароля (pending_rotate_username) сбрасывали только nav:*,
udev:, vpn:*, /start, /cancel и «Меню». После rotpick:alice → «Сервер» →
«Бэкап» → «Нет» любой следующий текст («привет») становился паролем alice.
Теперь любой колбэк-маршрут бросает все ожидания текстового ввода (как
раньше — только add-flow); маршрут, начинающий ожидание, ставит его заново."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture()
def apply_mock(bot_tt, monkeypatch, tt_paths):
    # Настоящий credentials.toml: иначе _get_user_password падает раньше
    # apply, и «не вызван» выполнялось бы впустую при любом коде.
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "alice"\npassword = "old"\n', encoding="utf-8")
    m = MagicMock(return_value=(None, None))
    monkeypatch.setattr(bot_tt, "_apply_rotate_password_sync", m)
    return m


def _route_handler(bot_tt, calls):
    async def dummy(update, context):
        calls.append(update.callback_query.data)

    route = bot_tt.CallbackRoute("dummy", r"^srv:", dummy, busy=False)
    return bot_tt.build_callback_query_handler(route).callback


def test_any_route_abandons_rotate_wait(
    bot_tt, apply_mock, allowed_update, allowed_callback_update, context, run_async
):
    # Сброс делает обёртка маршрута, а не конкретный хендлер: одного
    # маршрута-заглушки достаточно, callback_data на путь не влияет.
    data = "bak:no"
    calls: list[str] = []
    handler = _route_handler(bot_tt, calls)
    context.user_data["pending_rotate_username"] = "alice"

    run_async(handler(allowed_callback_update(data), context))
    run_async(bot_tt.rotate_password_input(allowed_update("привет"), context))

    assert calls == [data]
    apply_mock.assert_not_called()


def test_any_route_abandons_search_wait(bot_tt, allowed_callback_update, context, run_async):
    handler = _route_handler(bot_tt, [])
    context.user_data["pending_user_search"] = True

    run_async(handler(allowed_callback_update("srv:backup"), context))

    assert "pending_user_search" not in context.user_data


def test_abandoned_prompt_burned_but_source_message_kept(bot_tt, allowed_callback_update, context, run_async):
    handler = _route_handler(bot_tt, [])
    update = allowed_callback_update("srv:backup")
    src = update.callback_query.message
    context.bot.delete_message = AsyncMock()
    context.user_data["pending_rotate_username"] = "alice"
    context.user_data[bot_tt.ROTATE_SCAFFOLD_KEY] = [(src.chat_id, src.message_id), (src.chat_id, 42)]

    run_async(handler(update, context))

    deleted = [c.kwargs["message_id"] for c in context.bot.delete_message.await_args_list]
    assert deleted == [42]


def test_rotate_route_still_starts_wait(
    bot_tt, apply_mock, allowed_update, allowed_callback_update, context, run_async
):
    route = next(r for r in bot_tt.CALLBACK_ROUTES if r.handler is bot_tt.user_action_rotate_callback)
    handler = bot_tt.build_callback_query_handler(route).callback

    run_async(handler(allowed_callback_update("urot:alice"), context))
    assert context.user_data.get("pending_rotate_username") == "alice"

    run_async(bot_tt.rotate_password_input(allowed_update("new-pw"), context))
    apply_mock.assert_called_once()
    assert apply_mock.call_args.args[:2] == ("alice", "new-pw")


def test_search_wait_not_touched_without_pending(bot_tt, allowed_callback_update, context, run_async):
    """Без активного ожидания черновики поиска (выдача) не трогаем."""
    handler = _route_handler(bot_tt, [])
    context.bot.delete_message = AsyncMock()
    context.user_data[bot_tt.USER_SEARCH_SCAFFOLD_KEY] = [(111111, 77)]

    run_async(handler(allowed_callback_update("srv:backup"), context))

    context.bot.delete_message.assert_not_awaited()
