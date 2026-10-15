"""Тесты захвата окна: поиск окна, отслеживание, часть окна, интеграция с мониторингом."""

import numpy as np
import pytest

from settings import Crop, Region, Settings
from window_capture import (FOUND, MINIMIZED, MISSING, WindowInfo, WindowTracker,
                            bgra_has_content, crop_frame, cropped_area, match_window)

CHROME = WindowInfo(101, "Лекция 1 — Google Chrome", "Chrome_WidgetWin_1", "chrome.exe")
CHROME_2 = WindowInfo(102, "Почта — Google Chrome", "Chrome_WidgetWin_1", "chrome.exe")
ZOOM = WindowInfo(201, "Zoom Meeting", "ZPContentViewWndClass", "Zoom.exe")


class FakeApi:
    """Заглушка Windows API: список окон, их положение и содержимое."""

    def __init__(self, windows, frames=None, regions=None):
        self.windows = {w.hwnd: w for w in windows}
        self.frames = frames or {}
        self.regions = regions or {}

    def list_windows(self):
        return list(self.windows.values())

    def window_info(self, hwnd):
        return self.windows.get(hwnd)

    def client_region(self, hwnd):
        return self.regions.get(hwnd, Region(100, 50, 40, 30))

    def capture(self, hwnd):
        return self.frames.get(hwnd)


def frame(h=30, w=40, value=128):
    return np.full((h, w, 4), value, dtype=np.uint8)


# --- поиск окна ---

def test_match_by_exact_title():
    assert match_window([CHROME_2, CHROME], CHROME.title, CHROME.class_name, "chrome.exe") == CHROME


def test_match_by_type_when_title_changed():
    renamed = WindowInfo(103, "Лекция 2 — Google Chrome", CHROME.class_name, "chrome.exe")
    assert match_window([ZOOM, renamed], CHROME.title, CHROME.class_name, "chrome.exe") == renamed


def test_match_prefers_not_minimized():
    hidden = WindowInfo(104, "x", CHROME.class_name, "chrome.exe", minimized=True)
    assert match_window([hidden, CHROME_2], "нет такого", CHROME.class_name, "chrome.exe") == CHROME_2


def test_match_requires_same_program():
    other = WindowInfo(301, CHROME.title, CHROME.class_name, "msedge.exe")
    assert match_window([other], CHROME.title, CHROME.class_name, "CHROME.EXE") is None


def test_match_by_handle_first():
    assert match_window([CHROME, CHROME_2], CHROME.title, CHROME.class_name, "chrome.exe",
                        last_hwnd=102) == CHROME_2


# --- отслеживание окна ---

def test_tracker_states_and_reopen():
    api = FakeApi([CHROME])
    tracker = WindowTracker(CHROME.title, CHROME.class_name, CHROME.exe, api=api)
    assert tracker.update() == FOUND and tracker.window.hwnd == 101

    api.windows[101] = WindowInfo(101, "Новая вкладка — Google Chrome", CHROME.class_name,
                                  "chrome.exe", minimized=True)
    assert tracker.update() == MINIMIZED          # то же окно, свёрнуто (заголовок сменился)

    del api.windows[101]
    assert tracker.update() == MISSING            # программу закрыли

    api.windows[555] = WindowInfo(555, CHROME.title, CHROME.class_name, "chrome.exe")
    assert tracker.update() == FOUND              # открыли снова — найдено новое окно
    assert tracker.window.hwnd == 555


def test_tracker_ignores_reused_handle():
    api = FakeApi([CHROME])
    tracker = WindowTracker(CHROME.title, CHROME.class_name, CHROME.exe, api=api)
    tracker.update()
    api.windows = {101: WindowInfo(101, "Блокнот", "Notepad", "notepad.exe")}
    assert tracker.update() == MISSING            # дескриптор достался другой программе


def test_tracker_without_windows_api():
    tracker = WindowTracker("x", "y", "z.exe", api=None)
    tracker.api = None
    assert tracker.update() == MISSING


# --- часть окна ---

def test_crop_frame_and_area():
    full = np.arange(30 * 40 * 4, dtype=np.uint32).astype(np.uint8).reshape(30, 40, 4)
    crop = Crop(left=5, top=4, right=10, bottom=6)
    part, ok = crop_frame(full, crop)
    assert ok and part.shape == (20, 25, 4)
    assert np.array_equal(part, full[4:24, 5:30])
    area, ok = cropped_area(Region(100, 50, 40, 30), crop)
    assert ok and area == Region(105, 54, 25, 20)


def test_crop_grows_with_window():
    crop = Crop.from_box(10, 80, 900, 500, 1280, 720)
    assert crop.box(1280, 720) == (10, 80, 900, 500)
    assert crop.box(1920, 1080) == (10, 80, 1540, 860)    # окно растянули — часть выросла


def test_crop_too_small_window_falls_back_to_whole():
    crop = Crop(left=30, top=0, right=30, bottom=0)
    part, ok = crop_frame(frame(w=40), crop)
    assert not ok and part.shape == (30, 40, 4)


def test_black_frame_detection():
    assert not bgra_has_content(frame(value=0))
    black_with_alpha = frame(value=0)
    black_with_alpha[..., 3] = 255
    assert not bgra_has_content(black_with_alpha)
    assert bgra_has_content(frame(value=5))


def test_window_settings_roundtrip(tmp_path):
    from settings import load_settings, save_settings
    s = Settings(source_mode="window", window_title=CHROME.title, window_class=CHROME.class_name,
                 window_exe="chrome.exe", window_from_screen=True, window_crop=Crop(1, 2, 3, 4))
    save_settings(s, tmp_path / "s.json")
    assert load_settings(tmp_path / "s.json", tmp_path / "none.json") == s


# --- интеграция с потоком мониторинга ---

class FakeShot:
    def __init__(self, width, height, value=200):
        self.width, self.height, self.size = width, height, (width, height)
        self.bgra = bytes([value]) * (width * height * 4)


class FakeSct:
    def __init__(self):
        self.grabbed = []

    def grab(self, monitor):
        self.grabbed.append(monitor)
        return FakeShot(monitor["width"], monitor["height"])


@pytest.fixture
def monitor_with_window(qapp):
    from monitor import ChangeDetector, ScreenMonitor

    def make(api, **cfg):
        settings = Settings(source_mode="window", window_title=CHROME.title,
                            window_class=CHROME.class_name, window_exe="chrome.exe", **cfg)
        mon = ScreenMonitor(settings)
        mon._tracker = WindowTracker(CHROME.title, CHROME.class_name, "chrome.exe", api=api)
        mon.logs = []
        mon.log_message.connect(lambda text, level: mon.logs.append((level, text)))
        return mon, settings, ChangeDetector(1, 0, 0)
    return make


def test_grab_window_uses_window_content(monitor_with_window):
    api = FakeApi([CHROME], frames={101: frame(value=77)})
    mon, cfg, det = monitor_with_window(api)
    sct = FakeSct()
    got, area = mon._grab_window(sct, cfg, det)
    assert got.shape == (30, 40, 4) and got[0, 0, 0] == 77
    assert area == Region(100, 50, 40, 30)
    assert sct.grabbed == []                      # с экрана ничего не снимали


def test_grab_window_with_crop(monitor_with_window):
    api = FakeApi([CHROME], frames={101: frame(value=77)})
    mon, cfg, det = monitor_with_window(api, window_crop=Crop(5, 4, 10, 6))
    got, area = mon._grab_window(FakeSct(), cfg, det)
    assert got.shape == (20, 25, 4)
    assert area == Region(105, 54, 25, 20)


def test_grab_window_black_content_falls_back_to_screen(monitor_with_window):
    api = FakeApi([CHROME], frames={101: frame(value=0)})
    mon, cfg, det = monitor_with_window(api, window_crop=Crop(5, 4, 10, 6))
    sct = FakeSct()
    got, area = mon._grab_window(sct, cfg, det)
    assert sct.grabbed == [Region(105, 54, 25, 20).as_mss()]   # снята только нужная часть
    assert got.shape == (20, 25, 4) and got[0, 0, 0] == 200
    mon._grab_window(sct, cfg, det)
    assert sum("не отдаёт" in text for _, text in mon.logs) == 1   # предупреждение один раз


def test_grab_window_from_screen_option(monitor_with_window):
    api = FakeApi([CHROME], frames={101: frame(value=77)})
    mon, cfg, det = monitor_with_window(api, window_from_screen=True)
    sct = FakeSct()
    got, _ = mon._grab_window(sct, cfg, det)
    assert len(sct.grabbed) == 1 and got[0, 0, 0] == 200


def test_grab_window_waits_while_minimized_or_closed(monitor_with_window):
    minimized = WindowInfo(101, CHROME.title, CHROME.class_name, "chrome.exe", minimized=True)
    api = FakeApi([minimized], frames={101: frame()})
    mon, cfg, det = monitor_with_window(api)
    assert mon._grab_window(FakeSct(), cfg, det) is None
    assert mon._grab_window(FakeSct(), cfg, det) is None
    assert sum("свёрнуто" in text for _, text in mon.logs) == 1    # без повторов в журнале

    api.windows = {}
    assert mon._grab_window(FakeSct(), cfg, det) is None
    assert any("не найдено" in text for _, text in mon.logs)

    api.windows = {777: WindowInfo(777, CHROME.title, CHROME.class_name, "chrome.exe")}  # открыли снова
    api.frames = {777: frame(value=9)}
    got, _ = mon._grab_window(FakeSct(), cfg, det)
    assert got[0, 0, 0] == 9
    assert any("снова доступно" in text for _, text in mon.logs)
