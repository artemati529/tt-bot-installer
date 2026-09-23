"""systemctl is-active для упавшего/остановленного юнита печатает
failed/inactive и выходит с кодом 3. run_cmd(check=True) превращал это
в "" → карточки показывали «unknown» 🟡 вместо реального состояния 🔴."""
import subprocess


def _fake_is_active(state: str, rc: int):
    # Как настоящий run_process: check=True + ненулевой код → CommandError.
    def fake(cmd, **kwargs):
        if kwargs.get("check", True) and rc != 0:
            raise bot_tt_module().CommandError(f"{' '.join(cmd)} failed: {state}")
        return subprocess.CompletedProcess(cmd, rc, f"{state}\n", "")
    return fake


def bot_tt_module():
    import sys
    return sys.modules["bot_tt"]


def test_service_state_returns_failed_for_exit_code_3(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "run_process", _fake_is_active("failed", 3))
    assert bot_tt.service_state("trusttunnel.service") == "failed"


def test_service_state_unknown_when_systemctl_missing(bot_tt, monkeypatch):
    def fake(cmd, **kwargs):
        raise FileNotFoundError("systemctl")
    monkeypatch.setattr(bot_tt, "run_process", fake)
    assert bot_tt.service_state("trusttunnel.service") == "unknown"


def test_services_status_line_shows_failed_not_unknown(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "run_process", _fake_is_active("failed", 3))
    line = bot_tt._services_status_line()
    assert "failed" in line
    assert "unknown" not in line
    assert bot_tt._status_emoji("failed") != bot_tt._status_emoji("unknown")


def test_no_is_active_left_on_run_cmd(bot_tt):
    """run_cmd бросает ненулевой код — для is-active это неверно по определению."""
    import inspect
    src = inspect.getsource(bot_tt)
    assert 'run_cmd, ["systemctl", "is-active"' not in src
    assert 'run_cmd(["systemctl", "is-active"' not in src


def test_run_cmd_returns_empty_when_binary_missing(bot_tt, monkeypatch):
    def fake(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(bot_tt, "run_process", fake)
    assert bot_tt.run_cmd(["/opt/trusttunnel/trusttunnel_endpoint", "--version"]) == ""


def test_current_tt_version_unknown_when_binary_missing(bot_tt, tt_paths):
    # tt_paths направляет TT_DIR во временный каталог — бинарника там нет.
    assert bot_tt._get_current_tt_version_uncached() == "unknown"
    assert bot_tt.is_newer("v1.0.0", "unknown") is True
