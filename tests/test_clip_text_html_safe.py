"""clip_text резал текст посреди HTML: при длинном отчёте «Синхр. rules»
(~110+ лишних префиксов) <blockquote expandable><pre> оставался без
закрывающих тегов → Telegram BadRequest «can't parse entities», экран
молча не открывался. Плюс результат был на символ длиннее limit."""
from html.parser import HTMLParser


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


def _balanced(text: str) -> bool:
    p = _Balance()
    p.feed(text)
    p.close()
    return p.ok and not p.stack


def test_clip_text_never_exceeds_limit(bot_tt):
    out = bot_tt.clip_text("x" * 5000, 100)
    assert len(out) <= 100


def test_clip_text_short_text_untouched(bot_tt):
    assert bot_tt.clip_text("<b>hi</b>", 100) == "<b>hi</b>"


def test_clip_text_closes_open_tags(bot_tt):
    text = "<b>Заголовок</b>\n<blockquote expandable><pre>" + "\n".join(f"pfx{i:04d}" for i in range(2000)) + "</pre></blockquote>"
    out = bot_tt.clip_text(text, 500)
    assert len(out) <= 500
    assert _balanced(out), out[-80:]


def test_clip_text_does_not_cut_inside_tag_or_entity(bot_tt):
    text = "a" * 90 + '<a href="https://example.com/very/long">link</a>' + "&amp;" * 50
    for limit in range(60, 200):
        out = bot_tt.clip_text(text, limit)
        assert len(out) <= limit
        assert _balanced(out)
        body = out.split("\n\n...output truncated")[0]
        assert "<" not in body.rsplit(">", 1)[-1], f"обрыв внутри тега при limit={limit}"
        tail = body.rsplit("&", 1)[-1] if "&" in body else ";"
        assert ";" in tail or "&" not in body, f"обрыв внутри entity при limit={limit}"


def test_rules_sync_report_with_many_orphans_is_valid_html(bot_tt, tt_paths):
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "alice"\npassword = "pw"\n', encoding="utf-8")
    rules = "".join(
        f'[[rule]]\nclient_random_prefix = "{i:08x}"\naction = "allow"\n\n' for i in range(600)
    )
    tt_paths["RULES_FILE"].write_text(rules, encoding="utf-8")

    out = bot_tt.clip_text(bot_tt.build_rules_sync_report())

    assert len(out) <= bot_tt.CLIP_TEXT_LIMIT
    assert _balanced(out)
