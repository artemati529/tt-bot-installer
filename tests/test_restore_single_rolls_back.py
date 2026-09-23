"""Восстановление ОДНОГО файла при сбое apply_tt_config_change оставляло
на диске версию из бэкапа и возвращало (False, …): пользователь видел ❌,
файл при этом был изменён, а undo не выставлялся. restore_multiple в той
же ситуации откатывает — поведение должно совпадать."""


def _prepare(bot_tt, tt_paths):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    vpn = tt_paths["TT_DIR"] / "vpn.toml"
    vpn.write_text("in_tar = 1\n", encoding="utf-8")
    vpn.chmod(0o640)
    bot_tt.create_configs_backup()
    vpn.write_text("on_disk = 1\n", encoding="utf-8")
    return vpn


def test_restore_single_rolls_back_file_on_apply_failure(bot_tt, tt_paths, monkeypatch):
    vpn = _prepare(bot_tt, tt_paths)

    def boom(**kw):
        raise bot_tt.CommandError("restart failed")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", boom)
    monkeypatch.setattr(bot_tt, "_ensure_tt_running_best_effort", lambda: None)

    ok, _info = bot_tt.restore_file_from_latest_backup("vpn.toml")

    assert ok is False
    assert vpn.read_text(encoding="utf-8") == "on_disk = 1\n"
    assert vpn.stat().st_mode & 0o777 == 0o640


def test_restore_single_removes_file_that_did_not_exist_before(bot_tt, tt_paths, monkeypatch):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    rules = tt_paths["RULES_FILE"]
    rules.write_text("in_tar\n", encoding="utf-8")
    bot_tt.create_configs_backup()
    rules.unlink()

    def boom(**kw):
        raise bot_tt.CommandError("restart failed")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", boom)
    monkeypatch.setattr(bot_tt, "_ensure_tt_running_best_effort", lambda: None)

    ok, _info = bot_tt.restore_file_from_latest_backup("rules.toml")

    assert ok is False
    assert not rules.exists()


def test_restore_single_success_still_applies(bot_tt, tt_paths, monkeypatch):
    vpn = _prepare(bot_tt, tt_paths)
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: "restart")

    ok, _info = bot_tt.restore_file_from_latest_backup("vpn.toml")

    assert ok is True
    assert vpn.read_text(encoding="utf-8") == "in_tar = 1\n"
