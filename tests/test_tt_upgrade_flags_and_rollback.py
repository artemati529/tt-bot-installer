"""TrustTunnel upgrade must be non-interactive and rollback-capable."""
from unittest.mock import AsyncMock


def test_tt_install_sync_passes_auto_answer_and_pinned_version(bot_tt, monkeypatch):
    captured = {}

    def fake_run_shell(command, timeout=None, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return 0, "ok", ""

    monkeypatch.setattr(bot_tt, "run_shell", fake_run_shell)

    bot_tt._tt_install_sync("v1.2.3")

    assert "-a y" in captured["command"]
    assert "-V 1.2.3" in captured["command"]
    # Инсталлятор тянем с закреплённого release-тега, а не с master:
    # пользователь видит на карточке тег v1.2.3 — и получает именно его.
    assert "refs/tags/v1.2.3" in captured["command"]
    assert "refs/heads/master" not in captured["command"]
    assert captured["kwargs"]["capture_limit"] == 24000


def test_tt_install_sync_uses_pipefail(bot_tt, monkeypatch):
    """Without `set -o pipefail`, bash's pipeline exit code is curl|sh's
    LAST command (sh) — if curl fails (network/DNS/rate-limit/bad tag) with
    empty output, sh sees an empty script and exits 0. The upgrade task then
    thinks the install succeeded, starts the (unchanged) old binary, and
    reports "✅ TrustTunnel обновлён" with the OLD version — a silent no-op
    reported as success. Verified live: `curl <bad-url> | sh` really does
    exit 0 without pipefail, and exits with curl's real code with it."""
    captured = {}

    def fake_run_shell(command, timeout=None, **kwargs):
        captured["command"] = command
        return 0, "ok", ""

    monkeypatch.setattr(bot_tt, "run_shell", fake_run_shell)

    bot_tt._tt_install_sync("v1.2.3")

    assert "set -o pipefail" in captured["command"]


def test_backup_and_restore_tt_binary_roundtrip(bot_tt, tt_paths):
    binary = tt_paths["TT_DIR"] / "trusttunnel_endpoint"
    binary.write_bytes(b"old-version-bytes")
    original_mode = oct(binary.stat().st_mode)[-3:]

    assert bot_tt._backup_tt_binary() is True
    backup = tt_paths["TT_DIR"] / "trusttunnel_endpoint.bak"
    assert backup.read_bytes() == b"old-version-bytes"

    binary.write_bytes(b"broken-new-version")
    assert bot_tt._restore_tt_binary_backup() is True
    assert binary.read_bytes() == b"old-version-bytes"
    # Восстановление сохраняет исходный режим, а не затирает его.
    assert oct(binary.stat().st_mode)[-3:] == original_mode


def test_backup_returns_false_when_no_binary_present(bot_tt, tt_paths):
    assert bot_tt._backup_tt_binary() is False


def test_restore_returns_false_when_no_backup_present(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "trusttunnel_endpoint").write_bytes(b"whatever")
    assert bot_tt._restore_tt_binary_backup() is False


def test_tt_upgrade_task_rolls_back_when_new_version_fails_to_start(
    bot_tt, run_async, monkeypatch, tt_paths
):
    binary = tt_paths["TT_DIR"] / "trusttunnel_endpoint"
    binary.write_bytes(b"old-good-binary")

    monkeypatch.setattr(bot_tt, "_tt_stop_sync", lambda: None)
    monkeypatch.setattr(bot_tt, "_tt_install_sync", lambda version: (0, "installed", ""))

    def fail_start():
        raise bot_tt.CommandError("trusttunnel failed to become active")

    monkeypatch.setattr(bot_tt, "_tt_start_sync", fail_start)

    restart_calls = []
    monkeypatch.setattr(
        bot_tt,
        "run_process",
        lambda cmd, **kw: restart_calls.append(cmd),
    )

    bot = AsyncMock()

    run_async(bot_tt._tt_upgrade_task(bot, 111111, 77, {"current": "1.0.0", "latest": "v1.2.3"}))

    # The pre-update backup must be restored onto the binary path.
    assert binary.read_bytes() == b"old-good-binary"
    assert ["systemctl", "start", bot_tt.SERVICE_NAME] in restart_calls

    final_text = bot.edit_message_text.await_args.kwargs["text"]
    assert "✅" not in final_text
    assert "восстановлен" in final_text.lower()
