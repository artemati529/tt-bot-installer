"""Diagnostics, monitoring hub and debug menu are removed from the user-facing bot."""
import inspect


def _datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_no_debug_or_diagnostics_keyboards_left(bot_tt):
    assert not hasattr(bot_tt, "diag_inline_kb")
    assert not hasattr(bot_tt, "debug_menu_inline_kb")
    assert not hasattr(bot_tt, "debug_result_inline_kb")
    assert not hasattr(bot_tt, "debug_logs_inline_kb")
    assert not hasattr(bot_tt, "monitor_hub_kb")
    assert not hasattr(bot_tt, "UI_OPEN_MONITOR")
    assert not hasattr(bot_tt, "ui_open_monitor")


def test_no_debug_or_diagnostics_routes_registered(bot_tt):
    main_src = inspect.getsource(bot_tt.main)
    nav_src = inspect.getsource(bot_tt.nav_callback)
    logs_src = inspect.getsource(bot_tt.logs_filter_callback)

    for removed in ("nav:monitor", "nav:diag", "nav:debug", "diagnet", "dbg:", "dlogf:"):
        assert removed not in main_src
        assert removed not in nav_src
        assert removed not in logs_src


def test_server_hub_replaces_monitoring_with_certificate(bot_tt):
    datas = _datas(bot_tt.server_hub_kb())

    assert "nav:cert" in datas
    assert "nav:monitor" not in datas
    assert "nav:logs" not in datas
    assert "nav:diag" not in datas
    assert "nav:debug" not in datas
