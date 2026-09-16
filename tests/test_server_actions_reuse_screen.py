"""Server actions must reuse the tracked UI message."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_bot(context):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()


def _button_datas(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def _button_texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def test_confirm_kb_allows_custom_no_label(bot_tt):
    kb = bot_tt.confirm_kb("yes", "no", no_label="❌ Нет")

    assert _button_datas(kb) == ["yes", "no"]
    assert _button_texts(kb) == ["✅ Да", "❌ Нет"]


@pytest.fixture()
def tracked_context(bot_tt, context):
    _mock_bot(context)
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 111
    return context


def test_tap_restart_tt_reuses_tracked_screen(bot_tt, allowed_callback_update, tracked_context, run_async):
    update = allowed_callback_update("srv:restart")

    run_async(bot_tt.restart_tt_prompt_callback(update, tracked_context))

    tracked_context.bot.edit_message_text.assert_called_once()
    assert tracked_context.bot.edit_message_text.call_args.kwargs["message_id"] == 111
    tracked_context.bot.send_message.assert_not_called()


def test_run_backup_reuses_tracked_screen(bot_tt, tracked_context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "create_configs_backup", lambda: (Path("/tmp/x.tar.gz"), ["vpn.toml"]))

    run_async(bot_tt.run_backup(tracked_context.bot, 111111, context=tracked_context))

    assert tracked_context.bot.edit_message_text.call_count >= 1
    assert all(c.kwargs["message_id"] == 111 for c in tracked_context.bot.edit_message_text.call_args_list)
    tracked_context.bot.send_message.assert_not_called()


def test_srv_backup_opens_confirmation_without_running_backup(
    bot_tt, allowed_callback_update, tracked_context, run_async, monkeypatch
):
    run_backup = AsyncMock()
    monkeypatch.setattr(bot_tt, "run_backup", run_backup)
    update = allowed_callback_update("srv:backup")

    run_async(bot_tt.srv_callback(update, tracked_context))

    run_backup.assert_not_awaited()
    tracked_context.bot.edit_message_text.assert_awaited_once()
    kwargs = tracked_context.bot.edit_message_text.await_args.kwargs
    assert kwargs["message_id"] == 111
    assert "Бэкап конфигов" in kwargs["text"]
    assert _button_datas(kwargs["reply_markup"]) == ["bak:yes", "bak:no"]
    assert _button_texts(kwargs["reply_markup"]) == ["✅ Да", "❌ Нет"]
    tracked_context.bot.send_message.assert_not_called()


def test_backup_confirm_yes_runs_existing_backup_flow(
    bot_tt, allowed_callback_update, context, run_async, monkeypatch
):
    run_backup = AsyncMock()
    monkeypatch.setattr(bot_tt, "run_backup", run_backup)
    update = allowed_callback_update("bak:yes")

    run_async(bot_tt.backup_confirm_callback(update, context))

    run_backup.assert_awaited_once_with(context.bot, 111111, context=context)


def test_backup_confirm_no_returns_server_card(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("bak:no")

    run_async(bot_tt.backup_confirm_callback(update, context))

    update.callback_query.edit_message_text.assert_awaited_once()
    args = update.callback_query.edit_message_text.await_args
    assert args.args[0] == bot_tt.UI_OPEN_SERVER
    assert args.kwargs["parse_mode"] == bot_tt.ParseMode.HTML
    assert "srv:backup" in _button_datas(args.kwargs["reply_markup"])


def test_run_restore_pick_reuses_tracked_screen(bot_tt, tracked_context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "list_files_in_latest_backup", lambda: ["vpn.toml"])

    run_async(bot_tt.run_restore_pick(tracked_context.bot, 111111, context=tracked_context))

    tracked_context.bot.edit_message_text.assert_called_once()
    assert tracked_context.bot.edit_message_text.call_args.kwargs["message_id"] == 111
    tracked_context.bot.send_message.assert_not_called()


def test_run_os_upgrade_reuses_tracked_screen(bot_tt, tracked_context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_run_apt_update_sync", lambda: (0, "", ""))
    monkeypatch.setattr(bot_tt, "_run_apt_upgrade_sync", lambda: (0, "", ""))

    run_async(bot_tt.run_os_upgrade(tracked_context.bot, 111111, context=tracked_context))

    assert tracked_context.bot.edit_message_text.call_count >= 1
    assert all(c.kwargs["message_id"] == 111 for c in tracked_context.bot.edit_message_text.call_args_list)
    tracked_context.bot.send_message.assert_not_called()


def test_run_reboot_confirm_reuses_tracked_screen(bot_tt, tracked_context, run_async):
    run_async(bot_tt.run_reboot_confirm(tracked_context.bot, 111111, context=tracked_context))

    tracked_context.bot.edit_message_text.assert_called_once()
    assert tracked_context.bot.edit_message_text.call_args.kwargs["message_id"] == 111
    tracked_context.bot.send_message.assert_not_called()


def test_run_tt_upgrade_flow_reuses_tracked_screen(bot_tt, tracked_context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "_fetch_tt_versions", lambda: ("1.0.0", "1.0.0"))

    run_async(bot_tt.run_tt_upgrade_flow(tracked_context.bot, 111111, tracked_context))

    assert tracked_context.bot.edit_message_text.call_count >= 1
    assert all(c.kwargs["message_id"] == 111 for c in tracked_context.bot.edit_message_text.call_args_list)
    tracked_context.bot.send_message.assert_not_called()
