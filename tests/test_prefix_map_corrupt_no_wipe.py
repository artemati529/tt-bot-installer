"""Битый user_prefix_map.toml раньше читался как {} — авточистка при
add/delete считала сиротами ВСЕ allow-правила и стирала их, а следующая
запись карты затирала и остальные записи. Теперь битая карта — ошибка:
ни одна операция не должна продолжаться поверх неё."""
import pytest

CREDS = (
    '[[client]]\nusername = "alice"\npassword = "pw1"\n'
    '[[client]]\nusername = "bob"\npassword = "pw2"\n'
)
RULES = (
    '[[rule]]\nclient_random_prefix = "aa11"\naction = "allow"\n# user: alice\n\n'
    '[[rule]]\nclient_random_prefix = "bb22"\naction = "allow"\n# user: bob\n'
)
BROKEN_MAP = '[user_prefix]\nalice = "aa11"\nbroken = \n'


def _seed(tt_paths):
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    tt_paths["RULES_FILE"].write_text(RULES, encoding="utf-8")
    tt_paths["PREFIX_MAP_FILE"].write_text(BROKEN_MAP, encoding="utf-8")


def test_load_prefix_map_raises_on_corrupt_file(bot_tt, tt_paths):
    _seed(tt_paths)
    with pytest.raises(bot_tt.PrefixMapError):
        bot_tt._load_prefix_map()


def test_auto_cleanup_does_not_wipe_rules_when_map_corrupt(bot_tt, tt_paths):
    _seed(tt_paths)
    with pytest.raises(bot_tt.PrefixMapError):
        bot_tt._auto_cleanup_rules_orphans()
    assert tt_paths["RULES_FILE"].read_text(encoding="utf-8") == RULES


def test_delete_user_with_corrupt_map_leaves_every_store_untouched(bot_tt, tt_paths, monkeypatch):
    _seed(tt_paths)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: "restart")

    with pytest.raises(bot_tt.PrefixMapError):
        bot_tt._delete_user_and_restart_sync("bob")

    assert tt_paths["CRED_FILE"].read_text(encoding="utf-8") == CREDS
    assert tt_paths["RULES_FILE"].read_text(encoding="utf-8") == RULES
    assert tt_paths["PREFIX_MAP_FILE"].read_text(encoding="utf-8") == BROKEN_MAP


def test_add_user_with_corrupt_map_leaves_every_store_untouched(bot_tt, tt_paths, monkeypatch):
    _seed(tt_paths)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: "restart")
    monkeypatch.setattr(bot_tt, "generate_deeplink", lambda *a, **kw: "tt://x")

    with pytest.raises(bot_tt.PrefixMapError):
        bot_tt.add_user_and_make_link("carol", "pw3")

    assert tt_paths["CRED_FILE"].read_text(encoding="utf-8") == CREDS
    assert tt_paths["RULES_FILE"].read_text(encoding="utf-8") == RULES
    assert tt_paths["PREFIX_MAP_FILE"].read_text(encoding="utf-8") == BROKEN_MAP


def test_delete_user_rolls_back_when_failing_before_apply(bot_tt, tt_paths, monkeypatch):
    """Откат охватывал только apply_tt_config_change: исключение раньше
    (после того как credentials уже переписан) оставляло юзера удалённым."""
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    tt_paths["RULES_FILE"].write_text(RULES, encoding="utf-8")
    tt_paths["PREFIX_MAP_FILE"].write_text('[user_prefix]\nalice = "aa11"\nbob = "bb22"\n', encoding="utf-8")

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(bot_tt, "_remove_prefix_rules_for_user", boom)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: "restart")

    with pytest.raises(OSError):
        bot_tt._delete_user_and_restart_sync("bob")

    assert tt_paths["CRED_FILE"].read_text(encoding="utf-8") == CREDS
    assert "bob" in bot_tt._load_prefix_map()


def test_rules_sync_view_reports_corrupt_map(bot_tt, tt_paths, allowed_callback_update, context, run_async):
    _seed(tt_paths)
    update = allowed_callback_update("rulesync:view")

    run_async(bot_tt.rules_sync_callback(update, context))

    q = update.callback_query
    shown = q.edit_message_text.call_args
    assert shown is not None, "экран не обновился — ошибка ушла молча"
    assert "повреждён" in (shown.args[0] if shown.args else shown.kwargs["text"])
