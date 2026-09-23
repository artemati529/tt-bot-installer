"""Removed reply-keyboard and monitoring helpers must not linger."""
import inspect


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
