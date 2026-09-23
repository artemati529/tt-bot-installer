"""Откаты add/rotate/delete/restore возвращали файлы, но сервис не трогали:
если упал сам restart, после отката VPN оставался лежать до ручного
вмешательства. Теперь после отката — best-effort подъём, только если
сервис не active (сбой валидации не должен рвать живые сессии рестартом)."""
import pytest

CREDS = (
    '[[client]]\nusername = "alice"\npassword = "pw1"\n'
    '[[client]]\nusername = "bob"\npassword = "pw2"\n'
)


def _boom(**kw):
    raise RuntimeError("restart failed")


@pytest.fixture()
def starts(bot_tt, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(bot_tt, "_tt_start_best_effort", lambda: calls.append("start"))
    return calls


def test_ensure_running_starts_inactive_service(bot_tt, monkeypatch, starts):
    monkeypatch.setattr(bot_tt, "service_state", lambda unit, timeout=20: "failed")
    bot_tt._ensure_tt_running_best_effort()
    assert starts == ["start"]


def test_ensure_running_leaves_active_service_alone(bot_tt, monkeypatch, starts):
    monkeypatch.setattr(bot_tt, "service_state", lambda unit, timeout=20: "active")
    bot_tt._ensure_tt_running_best_effort()
    assert starts == []


def test_ensure_running_never_raises(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "service_state", lambda unit, timeout=20: "failed")

    def explode():
        raise OSError("no systemctl")

    monkeypatch.setattr(bot_tt, "_tt_start_best_effort", explode)
    bot_tt._ensure_tt_running_best_effort()


@pytest.fixture()
def service_down(bot_tt, monkeypatch, starts):
    monkeypatch.setattr(bot_tt, "service_state", lambda unit, timeout=20: "failed")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", _boom)
    return starts


def test_delete_rollback_brings_service_back(bot_tt, tt_paths, service_down):
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    with pytest.raises(RuntimeError):
        bot_tt._delete_user_and_restart_sync("bob")
    assert service_down == ["start"]


def test_rotate_rollback_brings_service_back(bot_tt, tt_paths, service_down):
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    with pytest.raises(RuntimeError):
        bot_tt._apply_rotate_password_sync("bob", "new-pw")
    assert service_down == ["start"]


def test_add_rollback_brings_service_back(bot_tt, tt_paths, service_down, monkeypatch):
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    monkeypatch.setattr(bot_tt, "generate_deeplink", lambda *a, **kw: "tt://x")
    with pytest.raises(RuntimeError):
        bot_tt.add_user_and_make_link("carol", "pw3")
    assert service_down == ["start"]


def test_restore_multiple_rollback_brings_service_back(bot_tt, tt_paths, service_down):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    bot_tt.create_configs_backup()
    ok, _ = bot_tt.restore_multiple_from_latest_backup(["credentials.toml"])
    assert ok is False
    assert service_down == ["start"]


def test_restore_single_rollback_brings_service_back(bot_tt, tt_paths, service_down):
    tt_paths["TT_DIR"].joinpath("backup").mkdir(parents=True, exist_ok=True)
    tt_paths["CRED_FILE"].write_text(CREDS, encoding="utf-8")
    bot_tt.create_configs_backup()
    ok, _ = bot_tt.restore_file_from_latest_backup("credentials.toml")
    assert ok is False
    assert service_down == ["start"]
