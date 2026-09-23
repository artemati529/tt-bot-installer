"""Обновление TT делалось как `curl … | sh`: sh исполняет скрипт по мере
поступления, и при обрыве загрузки успевает выполнить его начало (pipefail
лишь меняет итоговый код, но не отменяет уже выполненные строки). Теперь
установщик сначала целиком скачивается во временный файл и запускается,
только если curl завершился успешно."""
import os
import stat
import subprocess


def _run_generated(bot_tt, monkeypatch, tmp_path, curl_body: str) -> tuple[int, str]:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    curl = stub_dir / "curl"
    curl.write_text("#!/bin/sh\n" + curl_body, encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    marker = tmp_path / "executed"
    captured = {}

    def fake_run_shell(command, timeout=None, **kwargs):
        captured["command"] = command
        env = dict(os.environ, PATH=f"{stub_dir}:{os.environ['PATH']}", MARKER=str(marker))
        p = subprocess.run(["bash", "-c", command], env=env, check=False, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout, p.stderr

    monkeypatch.setattr(bot_tt, "run_shell", fake_run_shell)
    rc, _out, _err = bot_tt._tt_install_sync("v1.2.3")
    return rc, ("executed" if marker.exists() else "not-executed")


# curl-заглушка пишет скрипт в файл из `-o <path>` (или в stdout, если -o нет).
_WRITE = '''out=""
while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done
script='touch "$MARKER"'
if [ -n "$out" ]; then printf '%s\\n' "$script" > "$out"; else printf '%s\\n' "$script"; fi
'''


def test_truncated_download_is_not_executed(bot_tt, monkeypatch, tmp_path):
    rc, state = _run_generated(bot_tt, monkeypatch, tmp_path, _WRITE + "exit 18\n")
    assert rc != 0
    assert state == "not-executed", "недокачанный установщик всё равно запустился"


def test_failed_curl_reports_failure(bot_tt, monkeypatch, tmp_path):
    rc, state = _run_generated(bot_tt, monkeypatch, tmp_path, "exit 22\n")
    assert rc != 0
    assert state == "not-executed"


def test_complete_download_is_executed(bot_tt, monkeypatch, tmp_path):
    rc, state = _run_generated(bot_tt, monkeypatch, tmp_path, _WRITE + "exit 0\n")
    assert rc == 0
    assert state == "executed"
