"""Config backup writes must be atomic."""
import tarfile

import pytest


def test_backup_crash_mid_write_does_not_corrupt_previous_backup(bot_tt, tt_paths, monkeypatch):
    tt_dir = tt_paths["TT_DIR"]
    (tt_dir / "vpn.toml").write_text("v1 content", encoding="utf-8")

    backup_path, included = bot_tt.create_configs_backup()
    assert included == ["vpn.toml"]
    original_bytes = backup_path.read_bytes()
    assert len(original_bytes) > 0

    real_tarfile_open = tarfile.open

    def flaky_tarfile_open(path, mode):
        tar = real_tarfile_open(path, mode)

        def failing_add(*args, **kwargs):
            raise RuntimeError("simulated crash mid-write")

        tar.add = failing_add
        return tar

    monkeypatch.setattr(tarfile, "open", flaky_tarfile_open)

    with pytest.raises(RuntimeError):
        bot_tt.create_configs_backup()

    assert backup_path.read_bytes() == original_bytes, (
        "the previous good backup was destroyed by the interrupted write"
    )
