"""httpx/httpcore логировали на уровне INFO каждый HTTP-запрос
к Telegram (в т.ч. getUpdates раз в 10с) — journalctl тонул в шуме, реальные
события (наши callback start/done, ошибки) было не найти. Приглушаем оба логгера
до WARNING сразу после basicConfig.
"""
import logging


def test_httpx_and_httpcore_loggers_are_silenced_to_warning(bot_tt):
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
