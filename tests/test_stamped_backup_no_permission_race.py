"""_stamped_backup writing plaintext credentials must never expose the file
at loose (umask-default) permissions even transiently — the temp file
should be born restrictive, not chmod'd after the fact."""
import inspect
import os


def test_stamped_backup_file_never_wider_than_requested_mode(bot_tt, tmp_path, monkeypatch):
    # умышленно широкий umask — если write_text() создаёт файл до chmod,
    # temp-файл ловит этот umask на мгновение и мог быть прочитан извне.
    old_umask = os.umask(0o000)
    try:
        bot_tt._stamped_backup(tmp_path / "backup", "credentials", ".toml.bak", "secret=1\n", keep=5, file_mode=0o600)
    finally:
        os.umask(old_umask)

    files = list((tmp_path / "backup").glob("credentials-*.toml.bak"))
    assert len(files) == 1
    assert oct(files[0].stat().st_mode)[-3:] == "600"


def test_stamped_backup_writes_via_atomic_tmp_file_not_direct(bot_tt):
    # NamedTemporaryFile всегда рождается 0600 независимо от umask — прямой
    # path.write_text() на итоговый путь так не может, отсюда и гонка.
    src = inspect.getsource(bot_tt._stamped_backup)
    assert "NamedTemporaryFile" in src or "_atomic_write_bytes" in src
    assert ".write_text(" not in src
