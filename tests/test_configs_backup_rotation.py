"""Бэкап конфигов — один файл latest-configs.tar.gz, без дробления по датам:
ни restore, ни UI не дают выбрать что-то кроме latest."""
import tarfile


def test_configs_backup_keeps_only_the_single_latest_file(bot_tt, tt_paths):
    tt_dir = tt_paths["TT_DIR"]
    backup_dir = tt_dir / "backup"

    for i in range(4):
        (tt_dir / "vpn.toml").write_text(f"v{i}", encoding="utf-8")
        path, included = bot_tt.create_configs_backup()
        assert "vpn.toml" in included
        assert path == bot_tt.latest_backup_path()

    dated = list(backup_dir.glob("configs-*.tar.gz"))
    assert dated == [], f"не должно быть датированных архивов: {[p.name for p in dated]}"

    with tarfile.open(bot_tt.latest_backup_path(), "r:gz") as tar:
        f = tar.extractfile("vpn.toml")
        assert f.read() == b"v3"
