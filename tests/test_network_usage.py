"""Network usage line must stay compact."""


def test_network_usage_uses_arrows_without_boot_suffix(bot_tt, monkeypatch, tmp_path):
    net_dir = tmp_path / "ens3" / "statistics"
    net_dir.mkdir(parents=True)
    net_dir.joinpath("rx_bytes").write_text(str(59 * 1024**3), encoding="utf-8")
    net_dir.joinpath("tx_bytes").write_text(str(51 * 1024**3), encoding="utf-8")

    real_path = bot_tt.Path

    def fake_path(raw):
        raw_s = str(raw)
        prefix = "/sys/class/net/"
        if raw_s.startswith(prefix):
            return tmp_path / raw_s.removeprefix(prefix)
        return real_path(raw)

    monkeypatch.setattr(bot_tt, "Path", fake_path)
    monkeypatch.setattr(bot_tt, "run_cmd", lambda *a, **k: "ens3")

    result = bot_tt._network_iface_summary()

    assert result == "Сеть <code>ens3</code>: ↓ <code>59 GiB</code> · ↑ <code>51 GiB</code>"
    assert "RX" not in result
    assert "TX" not in result
    assert "с загрузки" not in result
