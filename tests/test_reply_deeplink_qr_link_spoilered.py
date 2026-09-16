"""reply_deeplink_with_qr — основной путь выдачи QR при создании/ротации —
клал пароль в URL нативной <a href> без спойлера, хотя у deeplink_spoiler_html
уже есть спойлер-обёртка для того же секрета, просто не применялась тут."""
from unittest.mock import AsyncMock, MagicMock


def test_deeplink_link_is_wrapped_in_spoiler(bot_tt, run_async):
    message = MagicMock()
    message.reply_photo = AsyncMock()

    run_async(bot_tt.reply_deeplink_with_qr(
        message,
        username="alice",
        deeplink="tt://?pw=supersecretpw",
        action_label=None,
        png=b"fake-png",
    ))

    caption = message.reply_photo.await_args.kwargs["caption"]
    assert "<tg-spoiler>" in caption
    assert caption.index("<tg-spoiler>") < caption.index("qr.html") < caption.index("</tg-spoiler>")
