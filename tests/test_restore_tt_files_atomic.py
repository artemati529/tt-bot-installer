"""_restore_tt_files wrote via plain Path.write_text — not atomic (no
tmp-file+os.replace), unlike every other write in the file. A kill mid-write
during a rollback (the one moment something already went wrong) could leave
a half-written credentials.toml. Now goes through _atomic_write_bytes with
the original file's mode explicitly preserved."""
import inspect


def test_restore_tt_files_uses_atomic_write(bot_tt):
    src = inspect.getsource(bot_tt._restore_tt_files)
    assert "_atomic_write_bytes" in src
    assert ".write_text(" not in src


def test_restore_tt_files_preserves_original_mode(bot_tt, tmp_path):
    f = tmp_path / "credentials.toml"
    f.write_text("old content", encoding="utf-8")
    f.chmod(0o600)

    snapshot = bot_tt._snapshot_tt_files([f])
    f.write_text("mutated", encoding="utf-8")
    f.chmod(0o644)  # simulate some other writer leaving it loose

    bot_tt._restore_tt_files(snapshot)

    assert f.read_text(encoding="utf-8") == "old content"
    assert oct(f.stat().st_mode)[-3:] == "600"


def test_snapshot_roundtrips_non_utf8_bytes(bot_tt, tmp_path):
    """Снапшот читал текст в UTF-8: файл с чужими байтами ронял сам снимок
    (UnicodeDecodeError) — и откат не мог начаться. Снимок — байты."""
    f = tmp_path / "rules.toml"
    raw = b"# \xff\xfe legacy\n"
    f.write_bytes(raw)
    snapshot = bot_tt._snapshot_tt_files([f])
    f.write_bytes(b"changed\n")
    bot_tt._restore_tt_files(snapshot)
    assert f.read_bytes() == raw
