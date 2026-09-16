"""Pytest fixtures for bot.py."""
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BOT_PATH = Path(__file__).resolve().parent.parent / "bot.py"
FAKE_ENV = (
    "BOT_TOKEN=123456:test-token\n"
    "ALLOWED_USER_ID=111111\n"
    "ENDPOINT_ADDRESS=vpn.example.com:443\n"
    "SERVER_NAME=testserver\n"
    "VPN_MONITOR_PORT=443\n"
)


def _load_bot_module():
    # TT_BOT_ENV_PATH делает ENV_PATH настраиваемым для импорта — реальный
    # временный файл вместо глобального патча Path.read_text.
    fd, env_path = tempfile.mkstemp(suffix=".env")
    with os.fdopen(fd, "w") as f:
        f.write(FAKE_ENV)
    os.environ["TT_BOT_ENV_PATH"] = env_path
    try:
        spec = importlib.util.spec_from_file_location("bot_tt", BOT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules["bot_tt"] = module
        spec.loader.exec_module(module)
    finally:
        os.environ.pop("TT_BOT_ENV_PATH", None)
        os.unlink(env_path)
    return module


@pytest.fixture(scope="session")
def bot_tt():
    return _load_bot_module()


@pytest.fixture()
def tt_paths(bot_tt, tmp_path, monkeypatch):
    """Point every on-disk config path the module uses at tmp_path."""
    paths = {
        "TT_DIR": tmp_path,
        "CRED_FILE": tmp_path / "credentials.toml",
        "RULES_FILE": tmp_path / "rules.toml",
        "PREFIX_MAP_FILE": tmp_path / "user_prefix_map.toml",
        "USER_PROFILES_FILE": tmp_path / "user_profiles.json",
        "BUSY_MARKER_FILE": tmp_path / ".tt-bot-busy",
    }
    for name, value in paths.items():
        monkeypatch.setattr(bot_tt, name, value)
    return paths


class FakeUser:
    def __init__(self, user_id: int, username: str = "admin"):
        self.id = user_id
        self.username = username


class FakeMessage:
    def __init__(self, text: str = "", chat_id: int = 111111, photo=None):
        self.text = text
        self.chat_id = chat_id
        self.photo = photo
        self.message_id = 1
        self.reply_text = AsyncMock()
        self.reply_photo = AsyncMock()
        self.edit_text = AsyncMock()


class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage | None = None):
        self.data = data
        self.message = message or FakeMessage()
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class FakeUpdate:
    def __init__(self, user_id: int = 111111, text: str = "", callback_data: str | None = None, chat_type: str = "private"):
        self.effective_user = FakeUser(user_id)
        self.effective_chat = MagicMock(id=user_id, type=chat_type)
        self.message = FakeMessage(text=text) if callback_data is None else None
        self.callback_query = FakeCallbackQuery(callback_data) if callback_data is not None else None


class FakeContext:
    def __init__(self):
        self.user_data = {}
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock()


@pytest.fixture()
def allowed_update():
    """A message-based update from the one allowed admin (id=111111, see FAKE_ENV)."""
    def _make(text: str = "", chat_type: str = "private"):
        return FakeUpdate(user_id=111111, text=text, chat_type=chat_type)
    return _make


@pytest.fixture()
def allowed_callback_update():
    def _make(data: str, chat_type: str = "private"):
        return FakeUpdate(user_id=111111, callback_data=data, chat_type=chat_type)
    return _make


@pytest.fixture()
def context():
    return FakeContext()


@pytest.fixture()
def run_async():
    def _run(coro):
        return asyncio.run(coro)
    return _run
