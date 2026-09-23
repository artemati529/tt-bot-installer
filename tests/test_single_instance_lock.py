import fcntl
import os

import pytest


def test_acquire_runtime_lock_rejects_second_instance(bot_tt, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_tt, "BOT_LOCK_PATH", tmp_path / "tt-bot.lock")
    first = bot_tt.acquire_runtime_lock()

    with pytest.raises(RuntimeError, match="уже запущен"):
        bot_tt.acquire_runtime_lock()

    first.close()
    second = bot_tt.acquire_runtime_lock()
    second.close()


def test_second_instance_does_not_wipe_pid_of_first(bot_tt, tmp_path, monkeypatch):
    """open("w") обрезал файл ДО flock: второй экземпляр стирал PID первого."""
    lock_path = tmp_path / "tt-bot.lock"
    monkeypatch.setattr(bot_tt, "BOT_LOCK_PATH", lock_path)
    first = bot_tt.acquire_runtime_lock()
    try:
        with pytest.raises(RuntimeError):
            bot_tt.acquire_runtime_lock()
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
    finally:
        fcntl.flock(first.fileno(), fcntl.LOCK_UN)
        first.close()


def test_lock_file_rewritten_on_reacquire(bot_tt, tmp_path, monkeypatch):
    lock_path = tmp_path / "tt-bot.lock"
    lock_path.write_text("99999\nstale\n", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "BOT_LOCK_PATH", lock_path)
    f = bot_tt.acquire_runtime_lock()
    f.close()
    assert lock_path.read_text(encoding="utf-8") == f"{os.getpid()}\n"
