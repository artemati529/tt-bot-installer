"""One-off inline messages should go through a single helper."""

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_send_inline_message_returns_sent_message(bot_tt, run_async):
    bot = MagicMock()
    sent = MagicMock(message_id=42)
    bot.send_message = AsyncMock(return_value=sent)
    kb = bot_tt.merge_inline_kb([bot_tt.InlineKeyboardButton("OK", callback_data="nav:home")])

    result = run_async(
        bot_tt.send_inline_message(
            bot,
            111111,
            "<b>hello</b>",
            parse_mode=bot_tt.ParseMode.HTML,
            reply_markup=kb,
        )
    )

    assert result is sent
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["reply_markup"] is kb
    assert bot.send_message.await_args.kwargs["disable_notification"] is True


def test_send_inline_message_rejects_reply_keyboard(bot_tt, run_async):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    reply_keyboard = MagicMock()
    reply_keyboard.keyboard = [["bad"]]

    with pytest.raises(TypeError, match="reply keyboard"):
        run_async(
            bot_tt.send_inline_message(
                bot,
                111111,
                "bad",
                reply_markup=reply_keyboard,
            )
        )


def test_plain_bot_send_message_calls_stay_behind_inline_helper_or_keyboard_cleanup(bot_tt):
    tree = ast.parse(inspect.getsource(bot_tt))
    allowed_callers = {
        "send_inline_message",
        "start",
    }
    direct_callers = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "send_message":
                caller = self.stack[-1] if self.stack else "<module>"
                if caller not in allowed_callers:
                    direct_callers.append((caller, node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)

    assert direct_callers == []
