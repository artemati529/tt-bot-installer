"""UI_MESSAGE_ID_KEY (which message is the current "home" card) and the
three scaffold trackers (USER_SEARCH_SCAFFOLD_KEY/ADD_FLOW_SCAFFOLD_KEY/
ROTATE_SCAFFOLD_KEY — burn-later prompt messages) all lived only in
context.user_data, in-memory, no persistence. Any tt-bot restart wiped
them: the home card lost its duplicate-prevention, and any scaffold prompt
mid-flow at restart time was orphaned in the chat forever. Now all four
are saved together to one small JSON file (no secrets — message ids only)
and restored into the Application's user_data before polling starts."""
from unittest.mock import AsyncMock, MagicMock


def test_save_and_load_ui_state_roundtrip(bot_tt, tmp_path, monkeypatch, context):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")
    bot_tt._ud(context)[bot_tt.UI_MESSAGE_ID_KEY] = 12345
    bot_tt._ud(context)[bot_tt.ROTATE_SCAFFOLD_KEY] = [(111, 222)]

    bot_tt._save_ui_state(context)
    state = bot_tt._load_ui_state()

    assert state["ui_message_id"] == 12345
    assert state[bot_tt.ROTATE_SCAFFOLD_KEY] == [[111, 222]]


def test_load_ui_state_missing_file_returns_empty(bot_tt, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "does-not-exist.json")

    assert bot_tt._load_ui_state() == {}


def test_load_ui_state_malformed_json_returns_empty(bot_tt, tmp_path, monkeypatch):
    path = tmp_path / "ui_state.json"
    path.write_text("not json{{{", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", path)

    assert bot_tt._load_ui_state() == {}


def test_set_ui_message_id_updates_context_and_persists(bot_tt, tmp_path, monkeypatch, context):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")

    bot_tt._set_ui_message_id(context, 777)

    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 777
    assert bot_tt._load_ui_state()["ui_message_id"] == 777


def test_track_scaffold_helpers_persist(bot_tt, tmp_path, monkeypatch, context):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")
    msg = MagicMock(chat_id=111111, message_id=42)

    bot_tt._track_user_search_message(context, msg)
    bot_tt._track_add_flow_message(context, msg)
    bot_tt._track_rotate_scaffold_message(context, msg)

    state = bot_tt._load_ui_state()
    for key in (bot_tt.USER_SEARCH_SCAFFOLD_KEY, bot_tt.ADD_FLOW_SCAFFOLD_KEY, bot_tt.ROTATE_SCAFFOLD_KEY):
        assert state[key] == [[111111, 42]]


def test_burn_scaffold_persists_after_clearing(bot_tt, tmp_path, monkeypatch, context, run_async):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")
    msg = MagicMock(chat_id=111111, message_id=42)
    bot_tt._track_rotate_scaffold_message(context, msg)

    bot = MagicMock()
    bot.delete_message = AsyncMock()
    run_async(bot_tt._burn_scaffold(bot, context, bot_tt.ROTATE_SCAFFOLD_KEY))

    assert bot_tt.ROTATE_SCAFFOLD_KEY not in bot_tt._load_ui_state()


def test_restore_ui_state_seeds_app_user_data(bot_tt, tmp_path, monkeypatch):
    from telegram.ext import Application

    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(bot_tt, "ALLOWED_USER_ID", 111111)
    bot_tt.UI_STATE_FILE.write_text(
        '{"ui_message_id": 555, "rotate_scaffold": [[111111, 42]]}', encoding="utf-8"
    )

    app = Application.builder().token("123:ABCDEFabcdefABCDEFabcdefABCDEFabcde").build()
    bot_tt._restore_ui_state(app)

    assert app.user_data[111111][bot_tt.UI_MESSAGE_ID_KEY] == 555
    assert app.user_data[111111][bot_tt.ROTATE_SCAFFOLD_KEY] == [(111111, 42)]


def test_restore_ui_state_does_nothing_without_saved_state(bot_tt, tmp_path, monkeypatch):
    from telegram.ext import Application

    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(bot_tt, "ALLOWED_USER_ID", 111111)

    app = Application.builder().token("123:ABCDEFabcdefABCDEFabcdefABCDEFabcde").build()
    bot_tt._restore_ui_state(app)

    assert bot_tt.UI_MESSAGE_ID_KEY not in app.user_data[111111]
