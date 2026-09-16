"""window_start=0.0 as a "never sent" sentinel collides with real
monotonic() values on low-uptime systems (monotonic() is seconds since
boot on Linux) — the very first error after a fresh boot+start could be
silently swallowed instead of sent immediately."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def test_first_error_sends_even_with_low_system_uptime(bot_tt, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_error_notify_state", {"window_start": None, "suppressed": 0})
    monkeypatch.setattr(bot_tt, "monotonic", lambda: 120.0)
    ctx = SimpleNamespace(bot=MagicMock(), error=RuntimeError("boom"))
    ctx.bot.send_message = AsyncMock(return_value=MagicMock())

    run_async(bot_tt.log_unhandled_error(None, ctx))

    ctx.bot.send_message.assert_awaited_once()
