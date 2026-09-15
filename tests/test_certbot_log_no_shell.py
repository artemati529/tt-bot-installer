"""get_certbot_log_tail: run_process списком аргументов, без shell."""


def test_returns_last_n_lines(bot_tt, tmp_path, monkeypatch):
    log = tmp_path / "letsencrypt.log"
    log.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "LE_LOG_FILE", log)

    result = bot_tt.get_certbot_log_tail(lines=3)

    assert "line8" in result
    assert "line9" in result
    assert "line10" in result
    assert "line1\n" not in result


def test_missing_file(bot_tt, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_tt, "LE_LOG_FILE", tmp_path / "nope.log")
    result = bot_tt.get_certbot_log_tail()
    assert "не найден" in result.lower()
