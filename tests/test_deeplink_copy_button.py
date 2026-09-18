"""reply_deeplink_with_qr's caption already hides the deeplink under a
spoiler — a CopyTextButton lets the admin copy it in one tap without
revealing/selecting text manually. Same _HAS_COPY_TEXT pattern already
used by _copy_host_button."""
from unittest.mock import AsyncMock, MagicMock


def test_qr_reply_has_copy_deeplink_button(bot_tt, run_async):
    message = MagicMock()
    message.reply_photo = AsyncMock()

    run_async(bot_tt.reply_deeplink_with_qr(
        message,
        username="alice",
        deeplink="tt://?pw=supersecretpw",
        action_label=None,
        png=b"fake-png",
    ))

    kb = message.reply_photo.await_args.kwargs["reply_markup"]
    buttons = [b for row in kb.inline_keyboard for b in row]
    copy_buttons = [b for b in buttons if getattr(b, "copy_text", None) is not None]
    assert len(copy_buttons) == 1
    assert copy_buttons[0].copy_text.text == "tt://?pw=supersecretpw"


def test_qr_reply_skips_copy_button_when_deeplink_too_long(bot_tt, run_async):
    """CopyTextButton.text is limited to 256 chars by Telegram (verified via
    telegram.constants.InlineKeyboardButtonLimit.MAX_COPY_TEXT) and PTB does
    not validate this client-side — an oversized value makes the whole
    sendPhoto call fail with BadRequest, losing the QR/deeplink delivery
    entirely for what would otherwise be a successful action. A long
    username (allowed up to 50 chars) combined with client_random_prefix
    routinely produces a deeplink past that limit."""
    message = MagicMock()
    message.reply_photo = AsyncMock()
    long_deeplink = "tt://?" + "x" * 300

    run_async(bot_tt.reply_deeplink_with_qr(
        message,
        username="alice",
        deeplink=long_deeplink,
        action_label=None,
        png=b"fake-png",
    ))

    kb = message.reply_photo.await_args.kwargs["reply_markup"]
    buttons = [b for row in kb.inline_keyboard for b in row]
    copy_buttons = [b for b in buttons if getattr(b, "copy_text", None) is not None]
    assert copy_buttons == []
