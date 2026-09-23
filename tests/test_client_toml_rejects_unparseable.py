"""Если вывод бинарника (--format toml) не разбирался как TOML,
_build_client_style_toml отдавал его пользователю как есть — в обход
_validate_client_toml, то есть без гарантии has_ipv6=false и нужных
секций. Теперь это ошибка: хендлер покажет «не удалось», а не битый файл."""
import pytest


def test_unparseable_endpoint_output_is_an_error(bot_tt):
    with pytest.raises(ValueError):
        bot_tt._build_client_style_toml("garbage [[[", protocol="h2", random_prefix=False, dns_upstreams=[])


def test_export_handler_reports_error_instead_of_sending_file(
    bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch
):
    from unittest.mock import AsyncMock

    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "alice"\npassword = "pw"\n', encoding="utf-8")
    monkeypatch.setattr(bot_tt, "generate_toml_config", lambda *a, **kw: "log line, not toml [[[\n")
    context.bot.send_document = AsyncMock()
    update = allowed_callback_update("tp:h2:alice")

    run_async(bot_tt.toml_export_callback(update, context))

    context.bot.send_document.assert_not_awaited()
