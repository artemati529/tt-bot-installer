"""Certbot log tail is long and rarely needs to stay open — wrap it in a
collapsible <blockquote expandable> instead of a flat wall of text."""
from unittest.mock import AsyncMock


def test_certbot_log_tail_wraps_snippet_in_expandable_blockquote(bot_tt, tmp_path, monkeypatch):
    log = tmp_path / "letsencrypt.log"
    log.write_text("line one\nline two\n", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "LE_LOG_FILE", log)

    text = bot_tt.get_certbot_log_tail(20)

    assert "<blockquote expandable>" in text
    assert "</blockquote>" in text
    assert text.index("<blockquote expandable>") < text.index("line one") < text.index("</blockquote>")


def test_certbot_log_tail_escapes_html_special_chars(bot_tt, tmp_path, monkeypatch):
    log = tmp_path / "letsencrypt.log"
    log.write_text("value <5 & ok>\n", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "LE_LOG_FILE", log)

    text = bot_tt.get_certbot_log_tail(20)

    assert "value &lt;5 &amp; ok&gt;" in text
    assert "<5" not in text


def test_cert_log_callback_uses_html_parse_mode(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "get_certbot_log_tail", lambda lines: "plain")
    update = allowed_callback_update("certlog:20")
    update.callback_query.edit_message_text = AsyncMock()

    run_async(bot_tt.cert_log_callback(update, context))

    kwargs = update.callback_query.edit_message_text.await_args.kwargs
    assert kwargs.get("parse_mode") == bot_tt.ParseMode.HTML
