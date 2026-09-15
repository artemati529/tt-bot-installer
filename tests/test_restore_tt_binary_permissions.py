"""_restore_tt_binary_backup: атомарная запись бинарника, режим не затирается
принудительным chmod 0750 — для non-root сервисного пользователя это теряло
execute-бит после отката неудавшегося апгрейда."""


def test_restore_preserves_existing_binary_mode(bot_tt, tt_paths):
    tt_dir = tt_paths["TT_DIR"]
    binary = tt_dir / "trusttunnel_endpoint"
    binary.write_bytes(b"old-version-bytes")
    binary.chmod(0o755)
    assert bot_tt._backup_tt_binary() is True
    binary.write_bytes(b"broken-new-version")

    assert bot_tt._restore_tt_binary_backup() is True

    assert binary.read_bytes() == b"old-version-bytes"
    assert oct(binary.stat().st_mode)[-3:] == "755"


def test_restore_creates_executable_when_target_missing(bot_tt, tt_paths):
    tt_dir = tt_paths["TT_DIR"]
    binary = tt_dir / "trusttunnel_endpoint"
    (tt_dir / "trusttunnel_endpoint.bak").write_bytes(b"old-version-bytes")
    assert not binary.exists()

    assert bot_tt._restore_tt_binary_backup() is True

    assert binary.read_bytes() == b"old-version-bytes"
    assert oct(binary.stat().st_mode)[-3:] == "755"


def test_restore_leaves_no_temp_files_behind(bot_tt, tt_paths):
    tt_dir = tt_paths["TT_DIR"]
    binary = tt_dir / "trusttunnel_endpoint"
    binary.write_bytes(b"old-version-bytes")
    binary.chmod(0o755)
    assert bot_tt._backup_tt_binary() is True

    bot_tt._restore_tt_binary_backup()

    leftovers = [p.name for p in tt_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
