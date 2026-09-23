"""Reply-клавиатура: ровно одна постоянная кнопка «🏠 Меню», не старая
многокнопочная панель и не «клавиатуры быть не должно» (см. test_menu_button.py
для самой кнопки и его логики)."""
import inspect
from unittest.mock import AsyncMock, MagicMock


class FakeSendableMessage:
    def __init__(self, chat_id=111111, message_id=1):
        self.chat_id = chat_id
        self.message_id = message_id
        self.delete = AsyncMock()
        self.reply_text = AsyncMock()


def _mock_bot(context):
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()


def test_send_home_screen_never_attaches_a_reply_keyboard(bot_tt, context, run_async):
    """send_home_screen сам по себе редактирует/шлёт только inline-карточку —
    носитель reply-клавиатуры «Меню» отправляется отдельно, в start()."""
    _mock_bot(context)

    run_async(bot_tt.send_home_screen(FakeSendableMessage(), context))

    for call in context.bot.send_message.call_args_list:
        rm = call.kwargs.get("reply_markup")
        assert not hasattr(rm, "keyboard"), "send_home_screen must not attach a ReplyKeyboardMarkup"


def test_main_registers_menu_button_early(bot_tt):
    src = inspect.getsource(bot_tt.main)

    assert "menu_button_tap" in src
    assert "group=-1" in src
