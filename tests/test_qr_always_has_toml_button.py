"""QR messages must always include the TOML button."""
import inspect
from unittest.mock import AsyncMock


class FakeMessage:
    def __init__(self, chat_id=111111, message_id=1):
        self.chat_id = chat_id
        self.message_id = message_id
        self.reply_text = AsyncMock()
        self.reply_photo = AsyncMock()
        self.delete = AsyncMock()


def test_reply_deeplink_with_qr_has_no_show_toml_button_param(bot_tt):
    params = inspect.signature(bot_tt.reply_deeplink_with_qr).parameters
    assert "show_toml_button" not in params


def test_qr_message_always_carries_a_toml_button(bot_tt, run_async):
    msg = FakeMessage()

    run_async(
        bot_tt.reply_deeplink_with_qr(
            msg,
            username="alice",
            deeplink="tt://?fake",
            action_label="повтор QR",
            png=b"fake-png",
        )
    )

    kb = msg.reply_photo.call_args.kwargs["reply_markup"]
    callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    caption = msg.reply_photo.call_args.kwargs["caption"]

    assert "utc:alice" in callback_datas
    assert "ulink:alice" not in callback_datas
    assert "udev:alice" not in callback_datas
    assert "nav:home" in callback_datas
    assert "Открыть deeplink trusttunnel.org/qr" in caption
    assert "Открыть trusttunnel.org/qr" not in caption
    assert msg.reply_photo.await_args.kwargs["disable_notification"] is True
