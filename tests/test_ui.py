"""Тесты интерфейса в «безэкранном» режиме Qt."""

import pytest

from settings import Region, Settings


def test_parse_hotkey():
    from ui import parse_hotkey
    assert parse_hotkey("Ctrl+Shift+S") == (["ctrl", "shift"], "S")
    assert parse_hotkey("ctrl + alt + f5") == (["ctrl", "alt"], "F5")
    assert parse_hotkey("S") is None
    assert parse_hotkey("Ctrl+Щ") is None
    assert parse_hotkey("Hyper+S") is None


def test_icons_render(qapp):
    from ui import app_icon, make_icon_pixmap
    assert not make_icon_pixmap(32, "active").isNull()
    assert not app_icon().isNull()


def test_region_conversion(qapp):
    from region_selector import region_on_screens, region_to_logical
    screen_rect = qapp.primaryScreen().geometry()
    region = Region(screen_rect.x() + 10, screen_rect.y() + 20, 100, 50)
    assert region_on_screens(region)
    screen, rect = region_to_logical(region)
    dpr = screen.devicePixelRatio()
    assert rect.width() == pytest.approx(100 / dpr)
    assert not region_on_screens(Region(-100000, -100000, 10, 10))


@pytest.fixture
def window(qapp, tmp_path):
    from ui import MainWindow
    win = MainWindow(Settings(save_dir=str(tmp_path / "shots")))
    yield win
    win.quit_app()


def test_start_without_region_is_refused(window):
    assert window.start_monitoring(interactive=False) is False
    assert window.monitor is None
    assert "не выбрана область" in window.log_view.toPlainText()


def test_start_with_unwritable_folder_is_refused(window, tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    window.settings.region = Region(0, 0, 50, 50)
    window.settings.save_dir = str(blocker / "sub")
    assert window.start_monitoring(interactive=False) is False
    assert "Нет доступа" in window.log_view.toPlainText()


def test_settings_changes_are_saved(window, isolated_config):
    from settings import load_settings
    window.threshold_spin.setValue(3.5)
    window.format_combo.setCurrentIndex(window.format_combo.findData("jpg"))
    window._save_settings_now()
    saved = load_settings(isolated_config / "settings.json")
    assert saved.threshold_percent == 3.5
    assert saved.image_format == "jpg"
    assert window.quality_spin.isEnabled()
