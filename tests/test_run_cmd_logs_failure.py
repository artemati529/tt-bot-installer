"""run_cmd не должен глотать ошибку молча: причина "unknown" в карточках
должна быть диагностируема по journalctl, а не угадываться по факту."""
import logging


def test_run_cmd_logs_failure_instead_of_silent_swallow(bot_tt, monkeypatch, caplog):
    def fake_run_process(cmd, **kwargs):
        raise bot_tt.CommandError("systemctl: connection timed out")

    monkeypatch.setattr(bot_tt, "run_process", fake_run_process)
    with caplog.at_level(logging.DEBUG, logger="tt-bot"):
        out = bot_tt.run_cmd(["systemctl", "is-active", "trusttunnel.service"])

    assert out == ""
    joined = " ".join(caplog.messages)
    assert "systemctl" in joined, "команда не попала в лог"
    assert "timed out" in joined, "причина ошибки не попала в лог"
    # Логгер по умолчанию INFO — ошибка должна быть на уровне, видимом в journalctl.
    assert any(
        r.levelno >= logging.WARNING and "timed out" in r.getMessage() for r in caplog.records
    ), "ошибка залогирована ниже WARNING — не будет видна при уровне INFO"
