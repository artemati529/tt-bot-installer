"""cert_log_callback/logs_filter_callback wrap the whole try in a bare
except that logged ANY failure (including a benign "message is not
modified" double-tap) as a full ERROR traceback. Already resolved once
both switched to safe_edit_message_text (which swallows that specific
BadRequest) — this locks the behavior in."""
import logging
from unittest.mock import AsyncMock

from telegram.error import BadRequest


def test_cert_log_not_modified_is_not_logged_as_error(bot_tt, allowed_callback_update, context, run_async, monkeypatch, caplog):
    monkeypatch.setattr(bot_tt, "get_certbot_log_tail", lambda lines: "same text")
    update = allowed_callback_update("certlog:20")
    update.callback_query.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified"))

    with caplog.at_level(logging.ERROR, logger="tt-bot"):
        run_async(bot_tt.cert_log_callback(update, context))

    assert caplog.records == []


def test_logs_filter_not_modified_is_not_logged_as_error(bot_tt, allowed_callback_update, context, run_async, monkeypatch, caplog):
    monkeypatch.setattr(bot_tt, "build_logs_view", lambda *a, **k: ("same text", 0, 1))
    update = allowed_callback_update("logf:all:50")
    update.callback_query.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified"))

    with caplog.at_level(logging.ERROR, logger="tt-bot"):
        run_async(bot_tt.logs_filter_callback(update, context))

    assert caplog.records == []
