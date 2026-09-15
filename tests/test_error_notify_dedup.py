"""log_unhandled_error не должен слать сообщение в админ-чат на каждую
несобранную ошибку — сетевой сбой означает N одинаковых "Внутренняя ошибка"
подряд. Дедуп: первое сообщение в окне (5 минут) уходит сразу, дальнейшие —
молча подсчитываются, а когда окно истекает — в тексте новой ошибки
упоминается, сколько было подавлено."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _fresh_context():
    ctx = SimpleNamespace(bot=MagicMock(), error=RuntimeError("boom"))
    ctx.bot.send_message = AsyncMock(return_value=MagicMock())
    return ctx


def test_only_first_error_in_window_sends_a_message(bot_tt, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_error_notify_state", {"window_start": 0.0, "suppressed": 0})
    context = _fresh_context()

    run_async(bot_tt.log_unhandled_error(None, context))
    run_async(bot_tt.log_unhandled_error(None, context))
    run_async(bot_tt.log_unhandled_error(None, context))

    assert context.bot.send_message.await_count == 1


def test_next_window_mentions_suppressed_count(bot_tt, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_error_notify_state", {"window_start": 0.0, "suppressed": 0})
    context = _fresh_context()
    fake_now = [1000.0]
    monkeypatch.setattr(bot_tt, "monotonic", lambda: fake_now[0])

    run_async(bot_tt.log_unhandled_error(None, context))  # sent (1st in window)
    run_async(bot_tt.log_unhandled_error(None, context))  # suppressed
    run_async(bot_tt.log_unhandled_error(None, context))  # suppressed
    fake_now[0] += 301  # окно истекло
    run_async(bot_tt.log_unhandled_error(None, context))  # sent, mentions +2

    assert context.bot.send_message.await_count == 2
    text = context.bot.send_message.await_args.kwargs["text"]
    assert "2" in text


def test_first_error_ever_still_sends_immediately(bot_tt, run_async, monkeypatch):
    # window_start=0.0 значит "никогда не отправляли" — первая же ошибка
    # не должна попасть в "подавленные" из-за monotonic() тоже начинающегося не с нуля.
    monkeypatch.setattr(bot_tt, "_error_notify_state", {"window_start": 0.0, "suppressed": 0})
    context = _fresh_context()

    run_async(bot_tt.log_unhandled_error(None, context))

    context.bot.send_message.assert_awaited_once()
    text = context.bot.send_message.await_args.kwargs["text"]
    assert "Внутренняя ошибка" in text
