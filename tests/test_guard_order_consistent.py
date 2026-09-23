"""Порядок обёрток был разным: в add-диалоге busy_guard(allow_guard(...)),
в маршрутах сброс add-flow → allow_guard → busy_guard. Итог:
- посторонний во время фоновой операции получал «Жди: …» (узнавал, что
  бот жив и чем занят) вместо «Нет доступа»;
- колбэк, отклонённый по busy, всё равно убивал add-flow и его scaffold;
- безобидную «Отмену» add-диалога нельзя было нажать во время операции."""
import pytest
from conftest import FakeUpdate


@pytest.fixture()
def busy(bot_tt, tt_paths):
    bot_tt.busy_set("обновление ОС")
    yield
    bot_tt.busy_clear()


def _conv(bot_tt):
    return bot_tt.build_add_conversation()


def test_stranger_gets_no_access_not_busy_on_add_entry(bot_tt, busy, context, run_async):
    entry = _conv(bot_tt).entry_points[0].callback
    update = FakeUpdate(user_id=999, callback_data="vpn:add")

    run_async(entry(update, context))

    text = update.callback_query.answer.await_args.kwargs.get("text") or ""
    assert "Нет доступа" in text
    assert "Жди" not in text


def test_add_cancel_works_while_busy(bot_tt, busy, allowed_callback_update, context, run_async):
    cancel = _conv(bot_tt).states[bot_tt.ASK_ADD_USERNAME][0].callback
    context.user_data["add_flow_active"] = True
    update = allowed_callback_update("addcancel")

    run_async(cancel(update, context))

    assert "add_flow_active" not in context.user_data


def test_busy_rejected_route_keeps_add_flow(bot_tt, busy, allowed_callback_update, context, run_async):
    route = next(r for r in bot_tt.CALLBACK_ROUTES if r.name == "vpn_hub_callback")
    assert route.busy
    handler = bot_tt.build_callback_query_handler(route).callback
    context.user_data["add_flow_active"] = True
    context.user_data["pending_add_username"] = "carol"
    update = allowed_callback_update("vpn:find")

    run_async(handler(update, context))

    assert context.user_data.get("add_flow_active") is True
    assert context.user_data.get("pending_add_username") == "carol"

