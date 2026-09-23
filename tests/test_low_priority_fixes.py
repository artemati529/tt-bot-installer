"""Мелкие дефекты: каждый — конкретный сценарий с неверным
результатом, который раньше не ловился тестами."""
import json
from unittest.mock import AsyncMock

import pytest

# --- версия TT после апгрейда -------------------------------------------------

def test_upgrade_reports_new_version_not_cached_old(bot_tt, run_async, monkeypatch, tt_paths):
    """tt_version кэшировался на 30с и не сбрасывался: быстрый апгрейд
    показывал «Новая версия: <старая>»."""
    versions = iter(["1.0.0", "1.2.3"])
    monkeypatch.setattr(bot_tt, "_get_current_tt_version_uncached", lambda: next(versions))
    bot_tt.MONITOR_CACHE.pop("tt_version", None)
    assert bot_tt.get_current_tt_version() == "1.0.0"  # экран проверки обновлений

    monkeypatch.setattr(bot_tt, "_tt_stop_sync", lambda: None)
    monkeypatch.setattr(bot_tt, "_backup_tt_binary", lambda: True)
    monkeypatch.setattr(bot_tt, "_tt_install_sync", lambda version: (0, "installed", ""))
    monkeypatch.setattr(bot_tt, "_tt_start_sync", lambda: None)
    bot = AsyncMock()

    run_async(bot_tt._tt_upgrade_task(bot, 111111, 77, {"current": "1.0.0", "latest": "v1.2.3"}))

    final_text = bot.edit_message_text.await_args.kwargs["text"]
    assert "1.2.3" in final_text
    bot_tt.MONITOR_CACHE.pop("tt_version", None)


# --- штампы бэкапов -----------------------------------------------------------

def test_stamped_backups_in_same_second_do_not_overwrite(bot_tt, tmp_path, monkeypatch):
    """Штамп с точностью до секунды: две записи подряд (repair: append +
    tag) затирали бэкап исходного состояния промежуточным."""
    monkeypatch.setattr(bot_tt, "_backup_timestamp", lambda: "20260923-101010")

    first = bot_tt._stamped_backup(tmp_path, "rules", ".toml", "ORIGINAL", keep=10)
    second = bot_tt._stamped_backup(tmp_path, "rules", ".toml", "INTERMEDIATE", keep=10)

    assert first != second
    assert first.read_text(encoding="utf-8") == "ORIGINAL"
    assert second.read_text(encoding="utf-8") == "INTERMEDIATE"


# --- битый user_profiles.json -------------------------------------------------

def test_corrupt_profiles_are_set_aside_not_wiped(bot_tt, tt_paths):
    """Битый JSON читался как {} и следующая запись затирала профили всех.
    Теперь исходник откладывается рядом (.corrupt-<штамп>) до записи."""
    broken = '{"alice": {"protocol": "quic", "random_prefix": true},'
    tt_paths["USER_PROFILES_FILE"].write_text(broken, encoding="utf-8")

    bot_tt._set_user_profile("bob", protocol="h2", random_prefix=False)

    saved = list(tt_paths["TT_DIR"].glob("user_profiles.json.corrupt-*"))
    assert len(saved) == 1
    assert saved[0].read_text(encoding="utf-8") == broken
    assert saved[0].stat().st_mode & 0o777 == 0o600
    assert "bob" in json.loads(tt_paths["USER_PROFILES_FILE"].read_text(encoding="utf-8"))


def test_valid_profiles_are_not_set_aside(bot_tt, tt_paths):
    tt_paths["USER_PROFILES_FILE"].write_text('{"alice": {"protocol": "h2"}}', encoding="utf-8")
    bot_tt._set_user_profile("bob", protocol="h2", random_prefix=False)
    assert not list(tt_paths["TT_DIR"].glob("user_profiles.json.corrupt-*"))


# --- ui_state.json ------------------------------------------------------------

def test_ui_state_write_is_atomic(bot_tt, tmp_path, monkeypatch, context):
    """write_text сначала обрезает файл: смерть процесса посреди записи
    оставляла пустой JSON и терялись ссылки на scaffold-сообщения."""
    state_file = tmp_path / "ui_state.json"
    state_file.write_text('{"ui_message_id": 1}', encoding="utf-8")
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", state_file)
    context.user_data[bot_tt.UI_MESSAGE_ID_KEY] = 2

    def crash(*a, **kw):
        raise OSError("killed mid-write")

    monkeypatch.setattr(bot_tt.os, "replace", crash)
    bot_tt._save_ui_state(context)

    assert state_file.read_text(encoding="utf-8") == '{"ui_message_id": 1}'


# --- невалидный UTF-8 в выводе команд ------------------------------------------

def test_run_process_tolerates_invalid_utf8(bot_tt):
    p = bot_tt.run_process(["printf", r"ok\377"], check=False)
    assert p.stdout.startswith("ok")


# --- load_env и кавычки -------------------------------------------------------

@pytest.mark.parametrize("raw", ['"123:abc"', "'123:abc'", "123:abc"])
def test_load_env_strips_matching_quotes(bot_tt, tmp_path, raw):
    env_file = tmp_path / ".env"
    env_file.write_text(f"BOT_TOKEN={raw}\n", encoding="utf-8")
    assert bot_tt.load_env(env_file)["BOT_TOKEN"] == "123:abc"


def test_load_env_keeps_unmatched_quote(bot_tt, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('SERVER_NAME="half\n', encoding="utf-8")
    assert bot_tt.load_env(env_file)["SERVER_NAME"] == '"half'


# --- правило-сирота при сбое внутри generate_deeplink ---------------------------

def test_add_user_rolls_back_rule_written_before_failure(bot_tt, tt_paths, monkeypatch):
    """Бинарник уже дописал allow-правило, а исключение случилось до
    made_rule_change — правило оставалось сиротой."""
    tt_paths["CRED_FILE"].write_text('[[client]]\nusername = "alice"\npassword = "pw"\n', encoding="utf-8")
    original_rules = '[[rule]]\ncidr = "10.0.0.0/8"\naction = "deny"\n'
    tt_paths["RULES_FILE"].write_text(original_rules, encoding="utf-8")
    monkeypatch.setattr(bot_tt, "_ensure_tt_running_best_effort", lambda: None)

    def fake_generate(username, **kw):
        with tt_paths["RULES_FILE"].open("a", encoding="utf-8") as f:
            f.write('\n[[rule]]\nclient_random_prefix = "ff00"\naction = "allow"\n')
        raise ValueError("deeplink validation failed")

    monkeypatch.setattr(bot_tt, "generate_deeplink", fake_generate)

    with pytest.raises(ValueError):
        bot_tt.add_user_and_make_link("carol", "pw3", random_prefix=True)

    assert tt_paths["RULES_FILE"].read_text(encoding="utf-8") == original_rules
    assert "carol" not in bot_tt.list_usernames()
