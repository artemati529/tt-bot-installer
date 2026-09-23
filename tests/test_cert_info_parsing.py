"""_cert_info_from_file/_cert_info_from_tls раньше дублировали разбор вывода
openssl построчно — вынесено в _parse_openssl_cert_output. Тестов на эти
функции не было вообще, добавляем, чтобы закрепить поведение.
"""

OPENSSL_OUT = "subject=CN = vpn.example.com\nnotAfter=Jun 13 12:00:00 2099 GMT\n"


def test_cert_info_from_file_parses_subject_and_enddate(bot_tt, tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    cert.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "run_argv", lambda *a, **k: (0, OPENSSL_OUT, ""))

    info = bot_tt._cert_info_from_file(cert)

    assert info["ok"] is True
    assert info["subject"] == "CN = vpn.example.com"
    assert info["not_after"] == "Jun 13 12:00:00 2099 GMT"
    assert info["path"] == str(cert)
    assert info["days"] is not None


def test_cert_info_from_file_missing_file(bot_tt, tmp_path):
    assert bot_tt._cert_info_from_file(tmp_path / "nope.pem")["ok"] is False


def test_cert_info_from_tls_parses_subject_and_enddate(bot_tt, monkeypatch):
    # s_client | x509 — настоящий пайп, остаётся на run_shell.
    monkeypatch.setattr(bot_tt, "run_shell", lambda *a, **k: (0, OPENSSL_OUT, ""))

    info = bot_tt._cert_info_from_tls("vpn.example.com", 443)

    assert info["ok"] is True
    assert info["subject"] == "CN = vpn.example.com"
    assert info["host"] == "vpn.example.com"


def test_cert_info_from_tls_empty_host(bot_tt):
    assert bot_tt._cert_info_from_tls("")["ok"] is False


def test_cert_info_returns_error_on_nonzero_exit(bot_tt, tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    cert.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "run_argv", lambda *a, **k: (1, "", "boom"))

    info = bot_tt._cert_info_from_file(cert)

    assert info["ok"] is False
    assert "boom" in info["error"]
