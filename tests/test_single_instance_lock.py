import pytest


def test_acquire_runtime_lock_rejects_second_instance(bot_tt, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_tt, "BOT_LOCK_PATH", tmp_path / "tt-bot.lock")
    first = bot_tt.acquire_runtime_lock()

    with pytest.raises(RuntimeError, match="уже запущен"):
        bot_tt.acquire_runtime_lock()

    first.close()
    second = bot_tt.acquire_runtime_lock()
    second.close()
