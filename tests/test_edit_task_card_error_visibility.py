"""_edit_task_card раньше ловил BadRequest и Exception с одинаковым debug-логом —
разделение было мёртвым (обе ветки делали одно и то же). Настоящие сетевые/API
сбои (TelegramError) — ожидаемы и остаются на debug; всё остальное — баг,
должно быть видно выше debug (logger.exception), но не ронять фон-задачу."""
import logging

from telegram.error import BadRequest, NetworkError


def test_message_not_modified_is_silent(bot_tt, run_async, caplog):
    bot = type("Bot", (), {})()

    async def fake_edit(**kwargs):
        raise BadRequest("Message is not modified")

    bot.edit_message_text = fake_edit
    with caplog.at_level(logging.DEBUG, logger="tt-bot"):
        run_async(bot_tt._edit_task_card(bot, 1, 2, "text"))
    assert caplog.records == []


def test_telegram_error_logged_at_debug_only(bot_tt, run_async, caplog):
    bot = type("Bot", (), {})()

    async def fake_edit(**kwargs):
        raise NetworkError("timed out")

    bot.edit_message_text = fake_edit
    with caplog.at_level(logging.DEBUG, logger="tt-bot"):
        run_async(bot_tt._edit_task_card(bot, 1, 2, "text"))
    assert any(r.levelno == logging.DEBUG for r in caplog.records)
    assert all(r.levelno < logging.WARNING for r in caplog.records)


def test_unexpected_error_is_swallowed_but_logged_above_debug(bot_tt, run_async, caplog):
    bot = type("Bot", (), {})()

    async def fake_edit(**kwargs):
        raise ValueError("unexpected bug")

    bot.edit_message_text = fake_edit
    with caplog.at_level(logging.DEBUG, logger="tt-bot"):
        run_async(bot_tt._edit_task_card(bot, 1, 2, "text"))  # не должно бросить наружу
    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        "неожиданная (не-Telegram) ошибка должна быть видна выше debug"
    )
