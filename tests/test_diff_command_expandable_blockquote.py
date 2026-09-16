"""/diff output can get long (multi-file unified diff) — wrap it in a
collapsible <blockquote expandable>, keeping the existing <pre> for
monospace formatting."""
from unittest.mock import AsyncMock


def test_diff_command_wraps_pre_in_expandable_blockquote(bot_tt, allowed_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_diff_against_latest_backup", lambda: "some diff text")
    update = allowed_update("")
    update.message.reply_text = AsyncMock()

    run_async(bot_tt.diff_command(update, context))

    text = update.message.reply_text.await_args.args[0]
    assert "<blockquote expandable><pre>" in text
    assert "</pre></blockquote>" in text
    assert "some diff text" in text
