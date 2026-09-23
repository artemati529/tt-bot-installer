"""Undo: один слот на пользователя, а у всех кнопок был одинаковый
callback_data «undo:go». «Отменить» под старым сообщением (удаление alice)
отменял последнее действие (смену пароля bob). Кроме того, отмена
восстановления файла не устаревала после других изменений этого файла и
не откатывалась при сбое apply."""
import hashlib
import re
from unittest.mock import AsyncMock

import pytest


@pytest.fixture()
def handlers(bot_tt, monkeypatch):
    calls = {"a": AsyncMock(), "b": AsyncMock()}
    monkeypatch.setitem(bot_tt._UNDO_HANDLERS, "kind_a", calls["a"])
    monkeypatch.setitem(bot_tt._UNDO_HANDLERS, "kind_b", calls["b"])
    return calls


def _answer_text(update):
    return update.callback_query.answer.await_args.kwargs.get("text") or ""


def test_stale_undo_button_does_not_undo_newer_action(bot_tt, handlers, allowed_callback_update, context, run_async):
    token_a = bot_tt._set_pending_undo(context, "kind_a", {"who": "alice"})
    token_b = bot_tt._set_pending_undo(context, "kind_b", {"who": "bob"})
    assert token_a != token_b

    update = allowed_callback_update(f"undo:{token_a}")
    run_async(bot_tt.undo_callback(update, context))

    handlers["a"].assert_not_awaited()
    handlers["b"].assert_not_awaited()
    assert "неактуальн" in _answer_text(update)
    # Слот не потрачен: кнопка под последним действием по-прежнему работает.
    run_async(bot_tt.undo_callback(allowed_callback_update(f"undo:{token_b}"), context))
    handlers["b"].assert_awaited_once()


def test_undo_row_carries_token_and_route_accepts_it(bot_tt, context):
    token = bot_tt._set_pending_undo(context, "kind_a", {})
    kb = bot_tt._with_undo_row(bot_tt.hub_inline_kb(), token)
    data = kb.inline_keyboard[0][0].callback_data
    assert data == f"undo:{token}"
    route = next(r for r in bot_tt.CALLBACK_ROUTES if r.handler is bot_tt.undo_callback)
    assert re.match(route.pattern, data)
    assert len(data.encode()) <= 64


def _restore_payload(target, prev: bytes, restored: bytes):
    return {
        "filename": target.name,
        "data": prev,
        "mode": 0o640,
        "restored_sha256": hashlib.sha256(restored).hexdigest(),
    }


def test_undo_restore_refuses_when_file_changed_since(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    target = tt_paths["CRED_FILE"]
    target.write_bytes(b"restored + carol added later\n")
    applied = []
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: applied.append(kw))
    token = bot_tt._set_pending_undo(context, "restore_file", _restore_payload(target, b"prev\n", b"restored\n"))

    update = allowed_callback_update(f"undo:{token}")
    run_async(bot_tt.undo_callback(update, context))

    assert target.read_bytes() == b"restored + carol added later\n"
    assert applied == []
    assert "изменён" in _answer_text(update)


def test_undo_restore_writes_back_when_unchanged(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    target = tt_paths["TT_DIR"] / "vpn.toml"
    target.write_bytes(b"restored\n")
    monkeypatch.setattr(bot_tt, "apply_tt_config_change", lambda **kw: "restart")
    token = bot_tt._set_pending_undo(context, "restore_file", _restore_payload(target, b"prev\n", b"restored\n"))

    run_async(bot_tt.undo_callback(allowed_callback_update(f"undo:{token}"), context))

    assert target.read_bytes() == b"prev\n"


def test_undo_restore_rolls_back_on_apply_failure(bot_tt, tt_paths, allowed_callback_update, context, run_async, monkeypatch):
    target = tt_paths["TT_DIR"] / "vpn.toml"
    target.write_bytes(b"restored\n")

    def boom(**kw):
        raise bot_tt.CommandError("validate failed")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", boom)
    monkeypatch.setattr(bot_tt, "_ensure_tt_running_best_effort", lambda: None)
    token = bot_tt._set_pending_undo(context, "restore_file", _restore_payload(target, b"prev\n", b"restored\n"))

    update = allowed_callback_update(f"undo:{token}")
    run_async(bot_tt.undo_callback(update, context))

    assert target.read_bytes() == b"restored\n", "файл остался откачен, хотя пользователь видит «не удалось»"
    assert "Не удалось" in _answer_text(update)
