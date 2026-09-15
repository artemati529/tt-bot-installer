"""Removed reply-keyboard and monitoring helpers must not linger."""
import inspect


def test_legacy_reply_keyboard_wrappers_are_removed(bot_tt):
    removed = (
        "add_entry",
        "html_expandable_blockquote",
        "ui_back_server",
        "tap_infosrv",
        "tap_infocli",
        "tap_logs",
        "tap_cert",
        "tap_rotate",
        "tap_export",
        "tap_list_delete",
        "tap_list_users",
        "tap_rules_sync",
        "tap_backup",
        "tap_restore_backup",
        "tap_os_upgrade",
        "tap_tt_upgrade",
        "tap_reboot_confirm",
        "run_cert",
        "run_infocli",
        "run_logs",
        "run_users_list",
        "run_rules_sync_view",
    )

    for name in removed:
        assert not hasattr(bot_tt, name), f"{name} must stay removed"

    assert hasattr(bot_tt, "add_entry_cb")
    assert hasattr(bot_tt, "tap_restart_tt")


def test_footer_navigation_has_no_monitor_compat_key(bot_tt):
    # nav_footer_row/card_footer_row объединены в один
    # BACK_PARENT + card_footer_row — "monitor" не должен всплыть ни там,
    # ни в вызывающих карточках (card_footer_row всегда падает на nav:home
    # для неизвестного parent, а не возвращает пустоту, как раньше умел
    # nav_footer_row).
    assert "monitor" not in bot_tt.BACK_PARENT
    assert bot_tt.card_footer_row("monitor")[0].callback_data == "nav:home"
    assert '"monitor"' not in inspect.getsource(bot_tt.card_footer_row)
    assert 'card_footer_row("monitor")' not in inspect.getsource(bot_tt.info_card_inline_kb)
    assert 'card_footer_row("monitor")' not in inspect.getsource(bot_tt.clients_inline_kb)
