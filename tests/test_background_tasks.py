import asyncio
from unittest.mock import AsyncMock, MagicMock


def _close_scheduled(scheduled):
    for coro in scheduled:
        close = getattr(coro, "close", None)
        if close:
            close()


def test_run_os_upgrade_schedules_background_task(bot_tt, context, run_async, monkeypatch):
    scheduled = []
    context.bot.send_message = AsyncMock()
    context.bot.send_message.return_value.message_id = 77
    monkeypatch.setattr(bot_tt, "_schedule_background_task", lambda ctx, coro: scheduled.append(coro), raising=False)

    def fail_if_called_sync():
        raise AssertionError("apt update must run in background task")

    monkeypatch.setattr(bot_tt, "_run_apt_update_sync", fail_if_called_sync)
    bot_tt.busy_clear()
    try:
        run_async(bot_tt.run_os_upgrade(context.bot, 111111, context=context))

        assert bot_tt.busy_label().startswith("обновление ОС")
        assert len(scheduled) == 1
        context.bot.send_message.assert_awaited_once()
        assert "Операция идёт в фоне" in context.bot.send_message.await_args.kwargs["text"]
    finally:
        bot_tt.busy_clear()
        _close_scheduled(scheduled)


def test_backup_confirm_callback_rejects_while_busy(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    """run_backup сам по себе больше не проверяет
    занятость — это делает единственный вызывающий, backup_confirm_callback,
    через _reject_if_busy (тот же, единый механизм busy, что и у ttupd/reboot)."""
    monkeypatch.setattr(
        bot_tt,
        "create_configs_backup",
        lambda: (_ for _ in ()).throw(AssertionError("backup must not run while busy")),
    )
    update = allowed_callback_update("bak:yes")

    bot_tt.busy_set("обновление ОС")
    try:
        run_async(bot_tt.backup_confirm_callback(update, context))
    finally:
        bot_tt.busy_clear()

    update.callback_query.answer.assert_awaited_once()
    assert "Жди: обновление ОС" in update.callback_query.answer.await_args.kwargs["text"]


def test_srv_osupd_tap_shows_confirm_even_while_busy(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    """srv:osupd — как и backup/restore/reboot/ttupd — только показывает
    confirm-карточку; занятость проверяется на самом confirm (osupd_yes),
    не раньше."""
    monkeypatch.setattr(
        bot_tt,
        "_run_apt_update_sync",
        lambda: (_ for _ in ()).throw(AssertionError("os upgrade must not run before confirm")),
    )
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    update = allowed_callback_update("srv:osupd")

    bot_tt.busy_set("бэкап конфигов")
    try:
        run_async(bot_tt.srv_callback(update, context))
    finally:
        bot_tt.busy_clear()

    update.callback_query.answer.assert_awaited_once()
    context.bot.send_message.assert_awaited_once()


def test_os_upgrade_confirm_rejects_while_busy(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    """osupd_yes — единственное место, где занятость реально проверяется
    для OS-upgrade, тем же механизмом, что и у backup/reboot."""
    monkeypatch.setattr(
        bot_tt,
        "_run_apt_update_sync",
        lambda: (_ for _ in ()).throw(AssertionError("os upgrade must not run while busy")),
    )
    update = allowed_callback_update("osupd_yes")

    bot_tt.busy_set("бэкап конфигов")
    try:
        run_async(bot_tt.os_upgrade_callback(update, context))
    finally:
        bot_tt.busy_clear()

    update.callback_query.answer.assert_awaited_once()
    assert "Жди: бэкап конфигов" in update.callback_query.answer.await_args.kwargs["text"]


def test_srv_backup_action_still_shown_while_busy(bot_tt, allowed_callback_update, context, run_async):
    """"Меню работает": тап действия под Сервер во время фоновой операции
    должен показать свою confirm-карточку, а не тост "Жди" — занятость
    проверяется только на самом confirm-шаге, не на первом тапе."""
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    update = allowed_callback_update("srv:backup")

    bot_tt.busy_set("обновление ОС")
    try:
        run_async(bot_tt.srv_callback(update, context))
    finally:
        bot_tt.busy_clear()

    context.bot.send_message.assert_awaited()


def test_update_tt_callback_schedules_background_task(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    scheduled = []
    monkeypatch.setattr(bot_tt, "_schedule_background_task", lambda ctx, coro: scheduled.append(coro), raising=False)
    monkeypatch.setattr(bot_tt, "_tt_stop_sync", lambda: (_ for _ in ()).throw(AssertionError("tt stop must be background")))
    context.user_data["pending_tt_update"] = {"current": "1.0.0", "latest": "1.1.0"}
    update = allowed_callback_update("ttupd_yes")
    bot_tt.busy_clear()
    try:
        run_async(bot_tt.update_tt_callback(update, context))

        assert bot_tt.busy_label().startswith("обновление TrustTunnel")
        assert len(scheduled) == 1
        assert "pending_tt_update" not in context.user_data
        update.callback_query.edit_message_text.assert_awaited_once()
        assert "Операция идёт в фоне" in update.callback_query.edit_message_text.await_args.args[0]
    finally:
        bot_tt.busy_clear()
        _close_scheduled(scheduled)


def test_schedule_background_task_retains_fallback_task_until_done(bot_tt, run_async):
    async def scenario():
        bot_tt.BACKGROUND_TASKS.clear()
        started = asyncio.Event()
        release = asyncio.Event()

        async def worker():
            started.set()
            await release.wait()

        bot_tt._schedule_background_task(None, worker())
        await started.wait()
        assert len(bot_tt.BACKGROUND_TASKS) == 1

        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(bot_tt.BACKGROUND_TASKS) == 0

    run_async(scenario())


def test_schedule_background_task_discards_failed_fallback_task(bot_tt, run_async):
    async def scenario():
        bot_tt.BACKGROUND_TASKS.clear()

        async def worker():
            raise RuntimeError("boom")

        bot_tt._schedule_background_task(None, worker())
        assert len(bot_tt.BACKGROUND_TASKS) == 1

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(bot_tt.BACKGROUND_TASKS) == 0

    run_async(scenario())
