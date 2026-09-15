"""is_allowed(update) не должен дублироваться вручную по всем хендлерам с
разным (случайным) поведением на отказ — часть callback-хендлеров отвечала
тостом "Нет доступа", часть молчала, а 4 функции (ui_back_home/ui_open_vpn/
ui_open_server/tap_restart_tt) вообще не нужно было проверять — они
достижимы только через уже проверенных вызывающих.

Точная карта 48 (пересчитана по коду, не по памяти):
- 31 — через build_callback_query_handler (все CallbackRoute)
- 7 — диалог добавления через build_add_conversation (entry + 4 состояния +
  cancel-фолбэк; cancel учитывается один раз здесь же, хотя регистрируется
  ещё и отдельной командой в main())
- 6 — прямые команды/сообщения в main() (start, menu_button_tap, myid,
  status, user_search_text, rotate_password_input)
- 4 — убраны вообще (ui_back_home, ui_open_vpn, ui_open_server, tap_restart_tt)

Итого 31+7+6+4 = 48. Гвард один (allow_guard), is_allowed(update) вызывается
теперь только внутри него.
"""
import inspect
import re
from unittest.mock import AsyncMock, MagicMock


def test_is_allowed_called_only_inside_allow_guard(bot_tt):
    src = inspect.getsource(bot_tt)
    assert len(re.findall(r"is_allowed\(update\)", src)) == 1


def test_allow_guard_denies_callback_query_with_toast(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)
    calls = []

    async def handler(update, ctx):
        calls.append(1)

    update = allowed_callback_update("nav:home")
    result = run_async(bot_tt.allow_guard(handler)(update, context))

    assert calls == []
    assert result is None
    update.callback_query.answer.assert_awaited_once()
    assert update.callback_query.answer.await_args.kwargs["text"] == "Нет доступа"
    assert update.callback_query.answer.await_args.kwargs["show_alert"] is True


def test_allow_guard_denies_plain_message_silently(bot_tt, allowed_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)
    calls = []

    async def handler(update, ctx):
        calls.append(1)

    update = allowed_update("hello")
    result = run_async(bot_tt.allow_guard(handler)(update, context))

    assert calls == []
    assert result is None


def test_allow_guard_conv_end_returns_conversation_end_on_denial(bot_tt, allowed_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)

    async def handler(update, ctx):
        return "should not be reached"

    update = allowed_update("hello")
    result = run_async(bot_tt.allow_guard(handler, conv_end=True)(update, context))

    assert result == bot_tt.ConversationHandler.END


def test_allow_guard_calls_through_when_allowed(bot_tt, allowed_callback_update, context, run_async):
    calls = []

    async def handler(update, ctx):
        calls.append(1)
        return "ok"

    update = allowed_callback_update("nav:home")
    result = run_async(bot_tt.allow_guard(handler)(update, context))

    assert calls == [1]
    assert result == "ok"
    assert update.callback_query.answer.await_count == 0


def test_every_callback_route_denies_unauthorized_user_with_toast(bot_tt, context, run_async, monkeypatch):
    """Раньше 10 из 31 маршрута молча возвращались на отказ (без тоста) —
    теперь единый allow_guard (внешний по отношению к любой логике самого
    хендлера, включая проверку q.data) даёт одинаковый ответ на всех 31,
    независимо от конкретных данных callback-query."""
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)

    for route in bot_tt.CALLBACK_ROUTES:
        handler = bot_tt.build_callback_query_handler(route).callback
        cq = MagicMock()
        cq.data = "irrelevant"
        cq.answer = AsyncMock()
        update = MagicMock()
        update.callback_query = cq
        update.effective_user = MagicMock(id=999999, username="nobody")
        update.effective_chat = MagicMock(id=999999)
        update.message = None

        run_async(handler(update, context))

        cq.answer.assert_awaited_once_with(text="Нет доступа", show_alert=True), route.name


def test_add_conversation_entry_denies_unauthorized_user(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)
    conv = bot_tt.build_add_conversation()
    entry_handler = conv.entry_points[0].callback

    update = allowed_callback_update("vpn:add")
    result = run_async(entry_handler(update, context))

    assert result == bot_tt.ConversationHandler.END
    update.callback_query.answer.assert_awaited_once_with(text="Нет доступа", show_alert=True)


def test_add_username_message_state_denies_unauthorized_user(bot_tt, allowed_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)
    conv = bot_tt.build_add_conversation()
    username_handlers = conv.states[bot_tt.ASK_ADD_USERNAME]
    message_handler = next(h for h in username_handlers if hasattr(h, "filters"))

    update = allowed_update("someusername")
    result = run_async(message_handler.callback(update, context))

    assert result == bot_tt.ConversationHandler.END


def test_ui_back_home_no_longer_checks_is_allowed_itself(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    """Убеждаемся, что убранная проверка не оставила дыру: без гварда
    вызывающего (nav_callback) is_allowed внутри ui_back_home больше нет —
    но реальный путь (через nav_callback) всё ещё защищён (см. тест ниже)."""
    src = inspect.getsource(bot_tt.ui_back_home)
    assert "is_allowed" not in src


def test_nav_callback_still_denies_unauthorized_user_end_to_end(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    """ui_back_home сам больше не проверяет доступ — но nav_callback (через
    build_callback_query_handler + allow_guard) обязан продолжать защищать
    весь путь nav:home end-to-end."""
    monkeypatch.setattr(bot_tt, "is_allowed", lambda update: False)
    route = next(r for r in bot_tt.CALLBACK_ROUTES if r.name == "nav_callback")
    handler = bot_tt.build_callback_query_handler(route).callback

    update = allowed_callback_update("nav:home")
    run_async(handler(update, context))

    update.callback_query.answer.assert_awaited_once_with(text="Нет доступа", show_alert=True)
