"""Тесты интерфейса в «безэкранном» режиме Qt."""

import pytest

from settings import Region, Settings


def test_parse_hotkey():
    from ui import parse_hotkey
    assert parse_hotkey("Ctrl+Alt+S") == (["ctrl", "alt"], "S")
    assert parse_hotkey("Meta+Shift+1") == (["win", "shift"], "1")
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


def test_start_refused_without_targets(window):
    window.settings.region = Region(0, 0, 50, 50)
    window.folder_check.setChecked(False)
    assert window.start_monitoring(interactive=False) is False
    assert "Не выбрано, куда сохранять" in window.log_view.toPlainText()


def test_start_refused_with_bad_document(window, tmp_path):
    window.settings.region = Region(0, 0, 50, 50)
    window.settings.docx_path = str(tmp_path / "notes.txt")
    window.docx_check.setChecked(True)
    assert window.start_monitoring(interactive=False) is False
    assert "расширение .docx" in window.log_view.toPlainText()


def test_timer_arms_and_stops_monitoring(window):
    from datetime import datetime, timedelta
    window.settings.region = Region(0, 0, 50, 50)
    window.timer_check.setChecked(True)
    window.timer_edit.setTime(window.timer_edit.time().fromString("1:30", "H:mm"))
    assert window.settings.timer_minutes == 90
    assert window.start_monitoring(interactive=False)
    assert window._deadline is not None
    assert timedelta(minutes=89) < window._deadline - datetime.now() <= timedelta(minutes=90)
    assert "Осталось 1:" in window.timer_left_label.text()
    window._deadline = datetime.now() - timedelta(seconds=1)   # время вышло
    window._on_countdown()
    assert window.monitor is None
    assert "остановлен автоматически" in window.log_view.toPlainText()
    assert window.timer_left_label.text() == ""


def test_timer_mode_at(window):
    from settings import TIMER_AT
    window.timer_mode_combo.setCurrentIndex(window.timer_mode_combo.findData(TIMER_AT))
    window.timer_edit.setTime(window.timer_edit.time().fromString("15:30", "H:mm"))
    assert window.settings.timer_mode == TIMER_AT
    assert window.settings.timer_at == "15:30"
    assert window.timer_hint.text() == "(время суток)"


def test_hotkey_can_be_changed(window):
    window._apply_hotkey("Ctrl+Alt+F9")
    assert window.settings.hotkey == "Ctrl+Alt+F9"
    window._apply_hotkey("Ctrl+Щ")                 # неподходящее сочетание не принимается
    assert window.settings.hotkey == "Ctrl+Alt+F9"
    assert "не подходит" in window.log_view.toPlainText()


# --- выбор окна ---

def test_window_mode_unavailable_off_windows(window):
    import ui
    if ui.WINDOW_CAPTURE_SUPPORTED:
        pytest.skip("проверка для систем без захвата окна")
    assert not window.window_radio.isEnabled()
    assert not window.select_window_btn.isEnabled()
    assert "только в Windows" in window.window_label.text()
    window.settings.source_mode = "window"
    assert window.start_monitoring(interactive=False) is False
    assert "только в Windows" in window.log_view.toPlainText()


def test_apply_window_and_crop(window, monkeypatch):
    import ui
    from settings import Crop
    from window_capture import WindowInfo
    monkeypatch.setattr(ui, "WINDOW_CAPTURE_SUPPORTED", True)   # подписи как в Windows
    info = WindowInfo(5, "Zoom Meeting", "ZPContentViewWndClass", "Zoom.exe")
    window._apply_window(info)
    s = window.settings
    assert (s.source_mode, s.window_title, s.window_exe) == ("window", "Zoom Meeting", "Zoom.exe")
    assert window.window_radio.isChecked()
    assert "[Zoom.exe] Zoom Meeting" in window.window_label.text()
    window._set_window_crop(Crop(10, 80, 300, 60))
    assert "часть окна" in window.crop_label.text()
    # Другое окно — прежняя область в нём сбрасывается
    window._apply_window(WindowInfo(6, "Блокнот", "Notepad", "notepad.exe"))
    assert s.window_crop is None and window.crop_label.text() == "Снимается: всё окно"
    # Выбор области экрана переключает обратно на режим «область»
    window._on_region_selected(Region(0, 0, 50, 50))
    assert s.source_mode == "region" and window.region_radio.isChecked()


def test_window_picker_dialog(qapp):
    import numpy as np

    from window_capture import WindowInfo
    from window_selector import WindowPickerDialog

    class Api:
        windows = [WindowInfo(1, "Лекция — Google Chrome", "Chrome_WidgetWin_1", "chrome.exe"),
                   WindowInfo(2, "Zoom Meeting", "ZPContentViewWndClass", "Zoom.exe", minimized=True)]

        def list_windows(self):
            return list(self.windows)

        def capture(self, hwnd):
            return np.full((60, 80, 4), 120, dtype=np.uint8)

    dialog = WindowPickerDialog(None, ("Zoom Meeting", "ZPContentViewWndClass", "Zoom.exe"), api=Api())
    texts = [dialog.list_widget.item(i).text() for i in range(dialog.list_widget.count())]
    assert texts[0] == "[chrome.exe] Лекция — Google Chrome"
    assert "(свёрнуто)" in texts[1]
    assert dialog.selected_window().exe == "Zoom.exe"            # выделено окно из настроек
    assert "свёрнуто" in dialog.preview.text()
    dialog.list_widget.setCurrentRow(0)
    assert not dialog.preview.pixmap().isNull()                  # превью показано
    dialog.search_edit.setText("zoom")
    assert dialog.list_widget.item(0).isHidden() and not dialog.list_widget.item(1).isHidden()
    assert dialog.selected_window().exe == "Zoom.exe"   # выделено первое подходящее окно
    dialog.crop_button.click()
    assert dialog.crop_requested and dialog.result() == 1


def test_window_crop_dialog_selection(qapp):
    import numpy as np
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    from settings import Crop
    from window_selector import WindowCropDialog

    dialog = WindowCropDialog(None, np.full((300, 400, 4), 90, dtype=np.uint8), None, "[x.exe] Окно")
    canvas = dialog.canvas
    canvas.resize(400, 300)                                     # масштаб 1:1
    assert dialog.crop() is None and "всё окно" in dialog.info.text()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(50, 40))
    QTest.mouseMove(canvas, QPoint(250, 200))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(250, 200))
    assert dialog.crop() == Crop(left=50, top=40, right=150, bottom=100)
    assert "200 × 160" in dialog.info.text()

    canvas.resize(800, 600)                                     # масштаб 2:1 — координаты окна те же
    assert dialog.crop() == Crop(left=50, top=40, right=150, bottom=100)
    dialog.canvas.clear()                                       # кнопка «Всё окно»
    assert dialog.crop() is None

    existing = WindowCropDialog(None, np.full((300, 400, 4), 90, dtype=np.uint8),
                                Crop(10, 20, 30, 40), "[x.exe] Окно")
    assert existing.crop() == Crop(10, 20, 30, 40)              # прежнее выделение показано


def test_browser_window_enables_tab_guard(window, monkeypatch):
    import ui
    from window_capture import WindowInfo
    monkeypatch.setattr(ui, "WINDOW_CAPTURE_SUPPORTED", True)
    window._apply_window(WindowInfo(7, "Лекция 5 — YouTube - Google Chrome", "Chrome_WidgetWin_1",
                                    "chrome.exe"))
    s = window.settings
    assert s.window_tab_only and s.window_title_filter == "Лекция 5 — YouTube"
    assert window.tab_check.isChecked() and window.tab_edit.text() == "Лекция 5 — YouTube"
    assert "только пока открыта вкладка" in window.log_view.toPlainText()
    # Ключевое слово вместо полного названия
    window.tab_edit.setText("YouTube")
    window._on_tab_guard_changed()
    assert s.tab_filter() == "YouTube"
    # Не браузер — защита вкладки выключена
    window._apply_window(WindowInfo(8, "Zoom Meeting", "ZPContentViewWndClass", "Zoom.exe"))
    assert not s.window_tab_only and s.tab_filter() == ""
