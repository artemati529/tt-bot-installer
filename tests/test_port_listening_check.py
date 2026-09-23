"""Diagnostics must include the VPN port listener check."""

from types import SimpleNamespace

LISTEN_OUTPUT = "State  Recv-Q Send-Q Local Address:Port  Peer Address:Port\nLISTEN 0      128    0.0.0.0:8443         0.0.0.0:*\n"
NOT_LISTENING_OUTPUT = "State  Recv-Q Send-Q Local Address:Port  Peer Address:Port\n"


def test_port_listening_summary_reports_ok_when_port_bound(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: LISTEN_OUTPUT)

    line = bot_tt._port_listening_summary(8443)

    assert line.startswith("🟢 ")
    assert "8443" in line
    assert "слушает" in line
    assert "НЕ слушает" not in line


def test_port_listening_summary_reports_fail_when_port_not_bound(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: NOT_LISTENING_OUTPUT)

    line = bot_tt._port_listening_summary(8443)

    assert line.startswith("🔴 ")
    assert "8443" in line
    assert "НЕ слушает" in line


def test_info_card_includes_port_check(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: LISTEN_OUTPUT)
    monkeypatch.setattr(bot_tt, "_tt_tls_port", lambda: 8443)
    monkeypatch.setattr(bot_tt, "_endpoint_metrics_hint", lambda: "🟢 метрики: доступны")
    monkeypatch.setattr(bot_tt, "_network_iface_summary", lambda: "сеть <code>eth0</code>: ↓ <code>1 MiB</code> · ↑ <code>2 MiB</code>")

    text = bot_tt.get_info_card_html()

    assert "🟢 порт 8443" in text
    assert "слушает" in text
    assert "🟢 метрики: доступны" in text


def test_info_card_is_compact_health_card_without_debug_diag_or_swap(bot_tt, monkeypatch):
    def fake_service_state(unit, *args, **kwargs):
        return "failed" if unit == "tt-bot.service" else "active"

    def fake_run_cmd(cmd, *args, **kwargs):
        if cmd[:2] == ["ss", "-ltn"]:
            return LISTEN_OUTPUT
        return ""

    def fail_run_shell(*args, **kwargs):
        raise AssertionError("Диагностика не должна читать journalctl")

    monkeypatch.setattr(bot_tt, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(bot_tt, "service_state", fake_service_state)
    monkeypatch.setattr(bot_tt, "run_shell", fail_run_shell)
    monkeypatch.setattr(bot_tt, "run_argv", fail_run_shell)
    monkeypatch.setattr(bot_tt.os, "getloadavg", lambda: (0.12, 0.08, 0.05))
    monkeypatch.setattr(bot_tt, "_uptime_pretty", lambda: "up 2 days, 3 hours")
    monkeypatch.setattr(bot_tt, "parse_meminfo", lambda: {"MemTotal": 1024 * 1000, "MemAvailable": 1024 * 512})
    monkeypatch.setattr(
        bot_tt.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            total=10 * 1024**3,
            used=4 * 1024**3,
            free=6 * 1024**3,
        ),
    )
    monkeypatch.setattr(bot_tt, "_tt_tls_port", lambda: 8443)
    monkeypatch.setattr(bot_tt, "get_cert_card_data", lambda: (_ for _ in ()).throw(AssertionError("Нагрузка не должна читать сертификат")))
    monkeypatch.setattr(bot_tt, "_endpoint_metrics_hint", lambda: "🟢 метрики: доступны")

    text = bot_tt.get_info_card_html()

    assert "🖥 Нагрузка" in text
    assert "Состояние:" in text
    assert "Сервисы" not in text
    assert "Подключение" not in text
    assert "Сертификат" not in text
    assert "ВМ" in text
    assert text.index("<b>ВМ</b>") < text.index("<b>Состояние:</b>")
    assert "Время работы: <code>up 2 days, 3 hours</code>" in text
    assert "🟢 TrustTunnel: <code>active</code>" in text
    assert "🔴 tt-bot: <code>failed</code>" in text
    assert "CPU: <code>0.12 / 0.08 / 0.05</code>" in text
    assert "RAM: <code>▓▓▓▓▓░░░░░ 49%</code> · <code>488/1000 MiB</code>" in text
    assert "Диск: <code>▓▓▓▓░░░░░░ 40%</code> · свободно <code>6 GiB</code>" in text
    assert "🟢 порт 8443: слушает" in text
    assert "🟢 метрики: доступны" in text
    assert "дней до конца" not in text
    assert "SWAP" not in text
    assert "Итог" not in text
    assert "Диагностика" not in text
    assert "DEBUG" not in text
    assert "Последние проблемные строки" not in text
    assert "journalctl" not in text


def test_metrics_hint_hides_raw_prometheus_help_text(bot_tt, tt_paths, monkeypatch):
    tt_paths["TT_DIR"].joinpath("vpn.toml").write_text(
        '[metrics]\naddress = "127.0.0.1:1987"\n',
        encoding="utf-8",
    )
    def fail_run_cmd(*args, **kwargs):
        raise AssertionError("Метрики не должны вызывать curl через subprocess")

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, *args):
            return b"# HELP client_sessions Number of active client sessions\nclient_sessions 1"

    def fake_urlopen(req, timeout):
        assert req.full_url == "http://127.0.0.1:1987/metrics"
        assert timeout == 3
        return FakeResponse()

    monkeypatch.setattr(bot_tt, "run_cmd", fail_run_cmd)
    monkeypatch.setattr(bot_tt.urllib.request, "urlopen", fake_urlopen)

    text = bot_tt._endpoint_metrics_hint()

    assert text == "🟢 метрики: доступны"
    assert "# HELP" not in text
    assert "client_sessions" not in text


def test_metrics_hint_handles_broken_vpn_toml_without_crashing(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("vpn.toml").write_text(
        "[metrics\n",
        encoding="utf-8",
    )

    text = bot_tt._endpoint_metrics_hint()

    assert text.startswith("🔴 метрики:")
    assert "vpn.toml" in text


def test_uptime_pretty_reads_proc_uptime_without_subprocess(bot_tt, monkeypatch, tmp_path):
    uptime_file = tmp_path / "uptime"
    uptime_file.write_text(str(2 * 86400 + 3 * 3600 + 4 * 60) + ".00 0.00\n", encoding="utf-8")
    real_path = bot_tt.Path

    def fake_path(raw):
        if str(raw) == "/proc/uptime":
            return uptime_file
        return real_path(raw)

    def fail_run_cmd(*args, **kwargs):
        raise AssertionError("Uptime не должен вызывать uptime -p через subprocess")

    monkeypatch.setattr(bot_tt, "Path", fake_path)
    monkeypatch.setattr(bot_tt, "run_cmd", fail_run_cmd)

    assert bot_tt._uptime_pretty() == "2 дня, 3 часа"
