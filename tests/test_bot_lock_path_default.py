"""BOT_LOCK_PATH default should be /run (root-only tmpfs, per-boot), not
/tmp (world-writable, symlink-attack surface for open("w"))."""


def test_bot_lock_path_defaults_to_run_not_tmp(bot_tt):
    assert str(bot_tt.BOT_LOCK_PATH) == "/run/tt-bot.lock"
