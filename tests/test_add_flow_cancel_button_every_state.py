"""«❌ Отмена» с первого экрана диалога добавления пользователя оставалась
висеть на экране, но состояния ASK_ADD_PASSWORD/ASK_ADD_PREFIX/ASK_ADD_PROTOCOL
не имели обработчика для "addcancel" — тап давал зависший спиннер и
диалог намертво застревал."""
from unittest.mock import AsyncMock


def _has_addcancel_handler(handlers):
    for h in handlers:
        pattern = getattr(h, "pattern", None)
        if pattern is not None and pattern.match("addcancel"):
            return h
    return None


def test_every_add_flow_state_handles_addcancel(bot_tt):
    conv = bot_tt.build_add_conversation()
    for state in (bot_tt.ASK_ADD_USERNAME, bot_tt.ASK_ADD_PASSWORD, bot_tt.ASK_ADD_PREFIX, bot_tt.ASK_ADD_PROTOCOL):
        handler = _has_addcancel_handler(conv.states[state])
        assert handler is not None, f"state {state} has no addcancel handler"


def test_addcancel_from_password_state_ends_conversation(bot_tt, allowed_callback_update, context, run_async):
    conv = bot_tt.build_add_conversation()
    handler = _has_addcancel_handler(conv.states[bot_tt.ASK_ADD_PASSWORD])
    assert handler is not None

    context.user_data["add_flow_active"] = True
    context.user_data["pending_add_username"] = "alice"
    update = allowed_callback_update("addcancel")
    update.callback_query.edit_message_text = AsyncMock()

    result = run_async(handler.callback(update, context))

    assert result == bot_tt.ConversationHandler.END
    assert "pending_add_username" not in context.user_data
