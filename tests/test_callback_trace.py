import inspect
import logging


def test_safe_callback_route_masks_user_arguments(bot_tt):
    assert bot_tt.safe_callback_route("nav:users:2") == "nav:users:2"
    assert bot_tt.safe_callback_route("udev:ivan") == "udev:<arg>"
    assert bot_tt.safe_callback_route("expproto:h2:ivan") == "expproto:h2:<arg>"


def test_safe_callback_route_masks_unknown_routes(bot_tt):
    # Неизвестные маршруты не должны проточить аргумент в журнал как есть.
    assert bot_tt.safe_callback_route("unknownroute:ivan") == "unknownroute:<unknown>"
    assert bot_tt.safe_callback_route("single") == "single:<unknown>"
    assert bot_tt.safe_callback_route(None) == "<empty>"


def test_safe_callback_route_logs_known_argless_subroutes_in_full(bot_tt):
    """Раньше был ручной whitelist из 6 записей против 31
    реального маршрута — nav:vpn/servercard/info/clients/close и т.п. (без
    пользовательского аргумента) утекали в журнал как nav:<unknown>, диагностика
    не диагностировала. Теперь известность маршрута берётся из самого
    CALLBACK_ROUTES, а не из отдельного списка."""
    assert bot_tt.safe_callback_route("nav:servercard") == "nav:servercard"
    assert bot_tt.safe_callback_route("nav:vpn") == "nav:vpn"
    assert bot_tt.safe_callback_route("vpn:add") == "vpn:add"
    assert bot_tt.safe_callback_route("srv:backup") == "srv:backup"
    assert bot_tt.safe_callback_route("rulesync:clean") == "rulesync:clean"


def test_callback_trace_logs_without_answering_query(bot_tt, allowed_callback_update, context, run_async, caplog):
    seen = []

    async def handler(update, ctx):
        seen.append((update, ctx))

    wrapped = bot_tt.traced_callback("test_handler", handler)
    update = allowed_callback_update("udev:ivan")

    with caplog.at_level(logging.INFO, logger="tt-bot"):
        run_async(wrapped(update, context))

    assert seen == [(update, context)]
    assert update.callback_query.answer.await_count == 0
    assert "route=udev:<arg>" in caplog.text
    assert "ivan" not in caplog.text


def test_callback_routes_are_registered_from_a_single_table(bot_tt):
    routes = {route.name: route for route in bot_tt.CALLBACK_ROUTES}

    assert routes["nav_callback"].pattern == r"^nav:"
    assert routes["nav_callback"].busy is False
    # srv_callback стал busy=False, чтобы "меню
    # работает" (обещание в карточках ОС/TT-апдейта) не было ложью для
    # ВСЕГО раздела Сервер — busy-проверка осталась точечно на osupd
    # (см. test_background_tasks.py::test_srv_osupd_rejects_while_busy).
    assert routes["srv_callback"].busy is False
    assert routes["reboot_callback"].pattern == r"^(rbdo|rbcancel)$"
    assert routes["reboot_callback"].busy is False
    assert routes["user_search_cancel_callback"].pattern == r"^searchcancel$"
    assert routes["user_search_cancel_callback"].busy is False
    assert routes["backup_confirm_callback"].pattern == r"^bak:(yes|no)$"
    assert routes["backup_confirm_callback"].busy is False

    main_src = inspect.getsource(bot_tt.main)
    assert "for route in CALLBACK_ROUTES" in main_src
    assert "CallbackQueryHandler(traced_callback(" not in main_src
