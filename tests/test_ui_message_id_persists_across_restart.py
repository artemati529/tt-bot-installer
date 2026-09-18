"""UI_MESSAGE_ID_KEY (какое сообщение сейчас "домашняя карточка") жило только
в context.user_data — в памяти процесса, без persistence. Любой рестарт
tt-bot стирал это значение, поэтому первый тап "🏠 Меню" после рестарта не
находил старую карточку для удаления и оставлял дубль в чате. Теперь ID
сохраняется в маленький JSON-файл (без секретов — просто число) и
подхватывается при старте бота."""


def test_save_and_load_ui_message_id_roundtrip(bot_tt, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")

    bot_tt._save_ui_message_id(12345)

    assert bot_tt._load_ui_message_id() == 12345


def test_load_ui_message_id_missing_file_returns_none(bot_tt, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "does-not-exist.json")

    assert bot_tt._load_ui_message_id() is None


def test_load_ui_message_id_malformed_json_returns_none(bot_tt, tmp_path, monkeypatch):
    path = tmp_path / "ui_state.json"
    path.write_text("not json{{{", encoding="utf-8")
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", path)

    assert bot_tt._load_ui_message_id() is None


def test_set_ui_message_id_updates_context_and_persists(bot_tt, tmp_path, monkeypatch, context):
    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")

    bot_tt._set_ui_message_id(context, 777)

    assert context.user_data[bot_tt.UI_MESSAGE_ID_KEY] == 777
    assert bot_tt._load_ui_message_id() == 777


def test_restore_ui_message_id_seeds_app_user_data(bot_tt, tmp_path, monkeypatch):
    from telegram.ext import Application

    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "ui_state.json")
    monkeypatch.setattr(bot_tt, "ALLOWED_USER_ID", 111111)
    bot_tt._save_ui_message_id(555)

    app = Application.builder().token("123:ABCDEFabcdefABCDEFabcdefABCDEFabcde").build()
    bot_tt._restore_ui_message_id(app)

    assert app.user_data[111111][bot_tt.UI_MESSAGE_ID_KEY] == 555


def test_restore_ui_message_id_does_nothing_without_saved_state(bot_tt, tmp_path, monkeypatch):
    from telegram.ext import Application

    monkeypatch.setattr(bot_tt, "UI_STATE_FILE", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(bot_tt, "ALLOWED_USER_ID", 111111)

    app = Application.builder().token("123:ABCDEFabcdefABCDEFabcdefABCDEFabcde").build()
    bot_tt._restore_ui_message_id(app)

    assert bot_tt.UI_MESSAGE_ID_KEY not in app.user_data[111111]
