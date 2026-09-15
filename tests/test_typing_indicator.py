"""Долгие фон-задачи (OS/TT upgrade, cert renew) должны слать typing,
чтобы UI не выглядел зависшим между обновлениями карточки прогресса."""
import asyncio
from unittest.mock import AsyncMock


def test_typing_while_sends_typing_action(bot_tt, run_async):
    bot = AsyncMock()

    async def scenario():
        async with bot_tt._typing_while(bot, 111111, interval=0.01):
            await asyncio.sleep(0.03)

    run_async(scenario())
    bot.send_chat_action.assert_awaited_with(chat_id=111111, action=bot_tt.ChatAction.TYPING)


def test_typing_while_stops_after_exit(bot_tt, run_async):
    bot = AsyncMock()

    async def scenario():
        async with bot_tt._typing_while(bot, 111111, interval=0.01):
            await asyncio.sleep(0.03)
        calls_at_exit = bot.send_chat_action.await_count
        await asyncio.sleep(0.05)
        assert bot.send_chat_action.await_count == calls_at_exit, "пульс должен остановиться после выхода"

    run_async(scenario())


def test_typing_while_survives_send_errors(bot_tt, run_async):
    bot = AsyncMock()
    bot.send_chat_action.side_effect = Exception("flood control")

    async def scenario():
        async with bot_tt._typing_while(bot, 111111, interval=0.01):
            await asyncio.sleep(0.03)  # не должно бросить наружу

    run_async(scenario())
