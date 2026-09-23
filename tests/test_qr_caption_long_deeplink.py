"""Подпись QR обрезалась по длине сырого HTML (с href), хотя лимит Telegram
(1024) считается ПОСЛЕ разбора entities — URL ссылки в него не входит.
Длинный deeplink (самоподписанный сертификат в TLV) → обрезка посреди
<a href>/<tg-spoiler> → BadRequest «can't parse entities», QR не уходил."""
import html
import re
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock


class _Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.ok = True

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.ok = False


def _visible_len(caption: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", caption)))


def _caption(bot_tt, run_async, monkeypatch, *, deeplink: str, username: str = "alice", mode_label=None) -> str:
    monkeypatch.setattr(bot_tt, "service_state", lambda unit, timeout=20: "active")
    message = MagicMock()
    message.reply_photo = AsyncMock()
    run_async(bot_tt.reply_deeplink_with_qr(
        message, username=username, deeplink=deeplink, action_label="создание пользователя",
        mode_label=mode_label, png=b"png",
    ))
    return message.reply_photo.await_args.kwargs["caption"]


def test_long_deeplink_keeps_full_link_and_valid_html(bot_tt, run_async, monkeypatch):
    deeplink = "tt://?" + "A" * 1500
    cap = _caption(bot_tt, run_async, monkeypatch, deeplink=deeplink)

    assert bot_tt.qr_page_url(deeplink) in html.unescape(cap), "ссылка обрезана"
    p = _Balance()
    p.feed(cap)
    assert p.ok and not p.stack, cap[-120:]
    assert _visible_len(cap) <= 1024


def test_overlong_visible_part_shortens_header_not_link(bot_tt, run_async, monkeypatch):
    deeplink = "tt://?" + "B" * 50
    cap = _caption(bot_tt, run_async, monkeypatch, deeplink=deeplink, mode_label="x" * 2000)

    assert _visible_len(cap) <= bot_tt.TG_CAPTION_SAFE
    assert bot_tt.qr_page_url(deeplink) in html.unescape(cap)
    assert cap.rstrip().endswith("</tg-spoiler>")
    p = _Balance()
    p.feed(cap)
    assert p.ok and not p.stack
