"""tomlkit бросает KeyAlreadyPresent (дубль ключа) НЕ как ValueError, в
отличие от ParseError: все `except ValueError` вокруг разбора TOML его
пропускали. Дубль ключа в vpn.toml ронял бот ещё на импорте
(_detect_tt_listen_port), а в конфигах проходил мимо validate."""
import pytest

DUP = 'listen_address = "0.0.0.0:443"\nlisten_address = "0.0.0.0:8443"\n'


def test_parse_toml_turns_duplicate_key_into_value_error(bot_tt):
    with pytest.raises(ValueError):
        bot_tt._parse_toml(DUP)


def test_detect_listen_port_survives_duplicate_key(bot_tt, tt_paths):
    (tt_paths["TT_DIR"] / "vpn.toml").write_text(DUP, encoding="utf-8")
    assert bot_tt._detect_tt_listen_port() is None


def test_prefix_map_duplicate_key_is_prefix_map_error(bot_tt, tt_paths):
    tt_paths["PREFIX_MAP_FILE"].write_text('[user_prefix]\na = "x"\na = "y"\n', encoding="utf-8")
    with pytest.raises(bot_tt.PrefixMapError):
        bot_tt._load_prefix_map()


def test_no_direct_tomlkit_parse_left(bot_tt):
    import inspect
    src = inspect.getsource(bot_tt)
    assert src.count("tomlkit.parse(") == 1, "разбор TOML только через _parse_toml"
