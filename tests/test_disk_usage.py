"""Disk usage must stay compact without spawning df."""

from types import SimpleNamespace


def test_disk_usage_uses_stdlib_not_df_subprocess(bot_tt, monkeypatch):
    def fail_run_cmd(*args, **kwargs):
        raise AssertionError("Диск не должен вызывать df через subprocess")

    monkeypatch.setattr(bot_tt, "run_cmd", fail_run_cmd)
    monkeypatch.setattr(
        bot_tt.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            total=100 * 1024**3,
            used=67 * 1024**3,
            free=33 * 1024**3,
        ),
    )

    result = bot_tt._disk_usage_summary()

    assert result.startswith("Диск:")
    assert "67%" in result
    assert "▓▓▓▓▓▓▓░░░ 67%" in result
    assert "33 GiB" in result
    assert "свободно" in result
    assert "диск /" not in result
    assert "Use%" not in result
    assert "Avail" not in result


def test_usage_bar_clamps_and_uses_ten_cells(bot_tt):
    assert bot_tt._usage_bar(0) == "░░░░░░░░░░ 0%"
    assert bot_tt._usage_bar(62) == "▓▓▓▓▓▓░░░░ 62%"
    assert bot_tt._usage_bar(100) == "▓▓▓▓▓▓▓▓▓▓ 100%"
    assert bot_tt._usage_bar(120) == "▓▓▓▓▓▓▓▓▓▓ 100%"
