"""Бэкапы credentials — это пароли всех клиентов.

Копии (credentials-*.toml.bak и restore-prev/credentials.toml.*) обязаны
быть доступны только владельцу: файл 0600, каталог 0700.
"""
import stat


def _mode(p):
    return stat.S_IMODE(p.stat().st_mode)


def test_credentials_backup_file_is_private(bot_tt, tt_paths):
    cred = tt_paths["CRED_FILE"]
    old_text = '[[client]]\nusername = "a"\npassword = "b"\n'
    cred.write_text(old_text, encoding="utf-8")

    bot_tt._atomic_write_credentials(
        '[[client]]\nusername = "a"\npassword = "c"\n', old_text
    )

    backups = sorted(
        (tt_paths["TT_DIR"] / "backup" / "credentials").glob("credentials-*.toml.bak")
    )
    assert backups, "credentials backup was not created"
    assert all(_mode(p) == 0o600 for p in backups), (
        f"credentials backup world-readable: {[oct(_mode(p)) for p in backups]}"
    )
    assert _mode(tt_paths["TT_DIR"] / "backup" / "credentials") == 0o700


def test_restore_prev_credentials_copy_is_private(bot_tt, tt_paths):
    cred = tt_paths["CRED_FILE"]
    cred.write_text('[[client]]\nusername = "a"\npassword = "b"\n', encoding="utf-8")
    cred.chmod(0o600)

    _, included = bot_tt.create_configs_backup()
    assert "credentials.toml" in included

    ok, info = bot_tt.restore_file_from_latest_backup("credentials.toml", restart_service=False)
    assert ok, info

    prev_files = list(
        (tt_paths["TT_DIR"] / "backup" / "restore-prev").glob("credentials.toml.*")
    )
    assert prev_files, "restore-prev copy was not created"
    assert all(_mode(p) == 0o600 for p in prev_files), (
        f"restore-prev credentials copy world-readable: {[oct(_mode(p)) for p in prev_files]}"
    )
