"""systemctl is-active после восстановления не должен блокировать event loop:
синхронный run_cmd внутри async-хендлера замораживает весь бот на весь timeout."""
import threading


def test_restore_callback_runs_systemctl_off_event_loop(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch
):
    tt_dir = tt_paths["TT_DIR"]
    (tt_dir / "rules.toml").write_text(
        "# user: x\n[[rule]]\nclient_random_prefix = \"abc\"\naction = \"allow\"\n",
        encoding="utf-8",
    )
    bot_tt.create_configs_backup()

    # Не даём restore дёргать реальный бинарник trusttunnel.
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **k: "restart")

    seen = {}

    def fake_run_cmd(cmd, *a, **k):
        seen["thread"] = threading.current_thread().name
        return "active"

    monkeypatch.setattr(bot_tt, "run_cmd", fake_run_cmd)

    update = allowed_callback_update("resdo:rules.toml")
    run_async(bot_tt.restore_backup_callback(update, context))

    assert "thread" in seen, "systemctl is-active не был вызван"
    assert seen["thread"] != threading.main_thread().name, (
        f"systemctl вызван на потоке event loop ({seen['thread']}) — блокирует весь бот"
    )
