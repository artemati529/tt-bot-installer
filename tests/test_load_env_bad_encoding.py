"""load_env не должен ронять весь бот на невалидном UTF-8 в .env
(например, оборванный байт кириллицы из-за локали терминала при вводе
SERVER_NAME на установке) — лучше кривое значение, чем сервис не стартует."""


def test_load_env_parses_valid_lines(bot_tt, tmp_path):
    p = tmp_path / ".env"
    p.write_text("BOT_TOKEN=123\nALLOWED_USER_ID=111\n", encoding="utf-8")
    env = bot_tt.load_env(p)
    assert env == {"BOT_TOKEN": "123", "ALLOWED_USER_ID": "111"}


def test_load_env_survives_invalid_utf8_byte(bot_tt, tmp_path):
    p = tmp_path / ".env"
    p.write_bytes(b"BOT_TOKEN=123\nSERVER_NAME=\xd0broken\nALLOWED_USER_ID=111\n")
    env = bot_tt.load_env(p)  # не должно бросить UnicodeDecodeError
    assert env["BOT_TOKEN"] == "123"
    assert env["ALLOWED_USER_ID"] == "111"
    assert "SERVER_NAME" in env
