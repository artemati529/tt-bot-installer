"""/diff-хендлер: шлёт результат _diff_against_latest_backup в <pre>."""
from unittest.mock import AsyncMock


def test_diff_command_replies_with_pre_block(bot_tt, tt_paths, allowed_update, context, run_async):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = 1\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = 2\n", encoding="utf-8")

    update = allowed_update("")
    update.message.reply_text = AsyncMock()

    run_async(bot_tt.diff_command(update, context))

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "<pre>" in args[0]
    assert "vpn.toml" in args[0]
    assert kwargs.get("parse_mode") == bot_tt.ParseMode.HTML


def test_diff_command_escapes_html(bot_tt, tt_paths, allowed_update, context, run_async):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = 1\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    (tt_paths["TT_DIR"] / "vpn.toml").write_text("a = '<b>x</b>'\n", encoding="utf-8")

    update = allowed_update("")
    update.message.reply_text = AsyncMock()

    run_async(bot_tt.diff_command(update, context))

    sent = update.message.reply_text.call_args[0][0]
    assert "<b>x</b>" not in sent
    assert "&lt;b&gt;" in sent
