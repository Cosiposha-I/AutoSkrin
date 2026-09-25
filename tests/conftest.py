"""Общие настройки тестов: путь к модулям проекта и «безэкранный» режим Qt."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Каждый тест работает со своей папкой настроек, а не с настоящей."""
    import settings
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(settings, "get_config_dir", lambda: config_dir)
    monkeypatch.setattr(settings, "get_config_path", lambda: config_dir / "settings.json")
    return config_dir
