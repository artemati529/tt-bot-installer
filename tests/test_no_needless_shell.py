"""Команды без пайпов и подстановок не должны идти через `bash -c`: сейчас
все аргументы экранированы или константы, но shell — лишняя поверхность,
которая выстрелит при первой неаккуратной правке. Здесь фиксируется, что
эти вызовы идут списком аргументов напрямую."""
import subprocess

import pytest


@pytest.fixture()
def argv_log(bot_tt, monkeypatch):
    calls: list[list[str]] = []

    def fake_run_process(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(bot_tt, "run_process", fake_run_process)
    bot_tt.MONITOR_CACHE.clear()
    yield calls
    bot_tt.MONITOR_CACHE.clear()


def _no_shell(calls):
    assert calls, "команда не вызвана"
    for cmd in calls:
        assert cmd[0] not in ("bash", "sh"), cmd


def test_cert_info_from_file_no_shell(bot_tt, tmp_path, argv_log):
    cert = tmp_path / "it's cert.pem"
    cert.write_text("x", encoding="utf-8")
    bot_tt._cert_info_from_file(cert)
    _no_shell(argv_log)
    assert str(cert) in argv_log[0]


def test_certbot_timer_no_shell(bot_tt, argv_log):
    bot_tt._certbot_timer_lines()
    _no_shell(argv_log)


def test_reload_check_no_shell(bot_tt, argv_log):
    bot_tt.service_reload_tls_if_possible()
    _no_shell(argv_log)


def test_port_listening_no_shell(bot_tt, argv_log):
    bot_tt._port_listening_summary(8443)
    _no_shell(argv_log)
    assert "sport = :8443" in argv_log[0]


@pytest.mark.parametrize("since", [None, "5 min ago"])
def test_logs_no_shell(bot_tt, argv_log, since):
    bot_tt._fetch_logs_raw(50, since=since)
    _no_shell(argv_log)


def test_run_argv_contract_on_timeout_and_missing_binary(bot_tt, monkeypatch):
    def timeout(cmd, **kw):
        raise bot_tt.CommandError("timeout after 1s")

    monkeypatch.setattr(bot_tt, "run_process", timeout)
    assert bot_tt.run_argv(["systemctl", "show"], timeout=1)[0] == 124

    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(bot_tt, "run_process", missing)
    code, _out, err = bot_tt.run_argv(["nope"], timeout=1)
    assert code == 127 and "nope" in err
