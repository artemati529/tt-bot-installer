"""Мёртвый код ловит vulture (requirements-dev): вернувшаяся неиспользуемая
функция (удалённые debug-меню, settings, cert-renew и т.п.) роняет тест.
Ограничение: vulture ищет имена по всему модулю — неиспользуемый параметр
с именем, которое где-то ещё используется (protocol), он НЕ видит; для
таких случаев остаются точечные тесты сигнатур (*_no_dead_*param*)."""
import subprocess
import sys
from pathlib import Path

import pytest

BOT_PATH = Path(__file__).resolve().parent.parent / "bot.py"


def test_bot_py_has_no_dead_code():
    pytest.importorskip("vulture")
    p = subprocess.run([sys.executable, "-m", "vulture", str(BOT_PATH)], check=False, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
