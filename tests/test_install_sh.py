"""install.sh ставится через `curl … | bash` от root:
- оборванная загрузка не должна выполнить полскрипта — тело в main(),
  вызов в последней строке;
- .env с BOT_TOKEN не должен ни мгновения быть читаемым всеми."""
import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"


def _bash(script: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True, timeout=30, **kw)


def test_install_sh_syntax_ok():
    assert subprocess.run(["bash", "-n", str(INSTALL_SH)], check=False).returncode == 0


def test_truncated_download_executes_nothing():
    text = INSTALL_SH.read_text(encoding="utf-8")
    half = text[: len(text) // 2]
    p = subprocess.run(["bash"], input=half, check=False, capture_output=True, text=True, timeout=30)
    # bash доходит до конца файла внутри незакрытого main() и падает с
    # syntax error, не выполнив ни одной команды. Без обёртки (не root)
    # сработала бы первая же проверка: «ERROR: Run this script as root».
    assert p.stdout == "", f"обрезанный скрипт что-то выполнил: {p.stdout}"
    assert "ERROR:" not in p.stderr and "==>" not in p.stderr, p.stderr


def test_main_is_invoked_on_last_line():
    lines = [ln for ln in INSTALL_SH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[-1].strip() == 'main "$@"'


def _func(name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def test_env_file_created_private_from_the_start(tmp_path):
    body = _func("write_env_file")
    p = _bash(
        _func("die") + body
        + f'umask 022; BOT_DIR="{tmp_path}"; BOT_TOKEN=t; ALLOWED_USER_ID=1; '
        'ENDPOINT_ADDRESS=a:1; SERVER_NAME=s; VPN_MONITOR_PORT=1; write_env_file; '
        f'stat -c %a "{tmp_path}/.env"'
    )
    assert p.stdout.strip() == "600", p.stderr
    assert "BOT_TOKEN=t" in (tmp_path / ".env").read_text()
    assert "umask 077" in body or "mktemp" in body


# --- угадывание адреса под set -euo pipefail ------------------------------------

def _guess(tmp_path, hosts: str, vpn: str) -> subprocess.CompletedProcess:
    (tmp_path / "hosts.toml").write_text(hosts, encoding="utf-8")
    (tmp_path / "vpn.toml").write_text(vpn, encoding="utf-8")
    return _bash(
        "set -euo pipefail\n" + _func("guess_hostname") + _func("guess_listen_port") + _func("guess_endpoint_address")
        + f'TT_DIR="{tmp_path}"; out="$(guess_endpoint_address)"; host="$(guess_hostname)"; echo "reached:$out|$host"'
    )


def test_guess_address_found(tmp_path):
    p = _guess(tmp_path, 'hostname = "vpn.example.com"\n', 'listen_address = "0.0.0.0:8443"\n')
    assert p.stdout.strip() == "reached:vpn.example.com:8443|vpn.example.com"


def test_guess_address_missing_does_not_kill_script(tmp_path):
    """grep без совпадений + pipefail → ненулевая подстановка → set -e молча
    завершал установщик уже после ввода токена, без единого сообщения."""
    p = _guess(tmp_path, "hostname = 'single-quoted.example'\n", "listen_address = '0.0.0.0:443'\n")
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "reached:|"


def test_hostname_guess_survives_missing_port(tmp_path):
    """Домен для certbot подсказывался из hosts.toml независимо от порта."""
    p = _guess(tmp_path, 'hostname = "vpn.example.com"\n', "listen_address = '0.0.0.0:443'\n")
    assert p.stdout.strip() == "reached:|vpn.example.com"


# --- повторный запуск ------------------------------------------------------------

def test_rerun_restarts_running_bot():
    """`enable --now` на уже активном юните — no-op: новый bot.py/.env не
    подхватывались, а скрипт печатал «Done»."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "systemctl enable --now tt-bot.service" not in text
    assert "systemctl restart tt-bot.service" in text


def test_rerun_keeps_manual_env_keys_and_backs_up(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "BOT_TOKEN=old\nALLOWED_USER_ID=1\nBACKUP_KEEP_CREDENTIALS=10\n# note\nMETRICS_CLIENTS_URL=http://x\n",
        encoding="utf-8",
    )
    p = _bash(
        _func("die") + _func("write_env_file")
        + f'BOT_DIR="{tmp_path}"; BOT_TOKEN=new; ALLOWED_USER_ID=2; '
        "ENDPOINT_ADDRESS=a:1; SERVER_NAME=s; VPN_MONITOR_PORT=1; write_env_file"
    )
    assert p.returncode == 0, p.stderr
    text = env.read_text(encoding="utf-8")
    assert "BOT_TOKEN=new" in text and "BOT_TOKEN=old" not in text
    assert "ALLOWED_USER_ID=2" in text
    assert "BACKUP_KEEP_CREDENTIALS=10" in text
    assert "METRICS_CLIENTS_URL=http://x" in text
    backups = list(tmp_path.glob(".env.bak-*"))
    assert len(backups) == 1 and "BOT_TOKEN=old" in backups[0].read_text(encoding="utf-8")
    assert backups[0].stat().st_mode & 0o777 == 0o600
