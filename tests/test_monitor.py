"""Тесты логики сравнения кадров, антиспам-защиты и сохранения файлов."""

from datetime import datetime

import numpy as np
import pytest
from PIL import Image

from monitor import (ChangeDetector, compute_change_percent, find_monitor, make_screenshot_path,
                     save_image)
from settings import Region


def frame(h=10, w=10, value=0):
    return np.full((h, w, 4), value, dtype=np.uint8)


def test_identical_frames_have_no_changes():
    assert compute_change_percent(frame(), frame()) == 0.0


def test_percent_of_changed_pixels():
    a, b = frame(), frame()
    b[0, :5, 2] = 200          # 5 пикселей из 100
    assert compute_change_percent(a, b) == pytest.approx(5.0)


def test_pixel_tolerance_ignores_noise():
    a, b = frame(value=100), frame(value=100)
    b[..., 0] = 110            # у всех пикселей синий канал +10
    assert compute_change_percent(a, b, pixel_tolerance=12) == 0.0
    assert compute_change_percent(a, b, pixel_tolerance=5) == 100.0


def test_no_uint8_overflow():
    a, b = frame(value=250), frame(value=5)
    assert compute_change_percent(a, b, pixel_tolerance=200) == 100.0
    assert compute_change_percent(b, a, pixel_tolerance=200) == 100.0


def test_alpha_channel_ignored():
    a, b = frame(), frame()
    b[..., 3] = 255
    assert compute_change_percent(a, b) == 0.0


def test_different_shapes_count_as_full_change():
    assert compute_change_percent(frame(10, 10), frame(10, 20)) == 100.0


def changed(value):
    return frame(value=value)


def test_detector_first_frame_is_baseline():
    d = ChangeDetector(threshold_percent=1, pixel_tolerance=0, min_interval_sec=0)
    assert not d.process(changed(0), 0).take_screenshot
    assert d.process(changed(50), 1).take_screenshot


def test_detector_threshold():
    d = ChangeDetector(threshold_percent=10, pixel_tolerance=0, min_interval_sec=0)
    d.process(frame(), 0)
    small = frame()
    small[0, :5] = 255         # 5 % < порога 10 %
    decision = d.process(small, 1)
    assert decision.percent == pytest.approx(5.0)
    assert not decision.changed and not decision.take_screenshot


def test_detector_accumulates_slow_changes():
    """Мелкие изменения накапливаются относительно эталонного кадра."""
    d = ChangeDetector(threshold_percent=10, pixel_tolerance=0, min_interval_sec=0)
    base = frame()
    d.process(base, 0)
    step1 = base.copy()
    step1[0, :6] = 255         # 6 %
    assert not d.process(step1, 1).take_screenshot
    step2 = step1.copy()
    step2[1, :6] = 255         # всего 12 % от эталона
    assert d.process(step2, 2).take_screenshot


def test_antispam_defers_and_then_takes_screenshot():
    d = ChangeDetector(threshold_percent=1, pixel_tolerance=0, min_interval_sec=5)
    d.process(changed(0), 0)
    first = d.process(changed(10), 1)
    assert first.take_screenshot
    d.mark_saved(1)

    second = d.process(changed(20), 2)          # изменение во время паузы
    assert not second.take_screenshot and second.deferred
    assert second.trigger_percent == pytest.approx(100.0)
    third = d.process(changed(30), 3)           # ещё одно — второй раз не сообщаем
    assert not third.take_screenshot and not third.deferred
    quiet = d.process(changed(30), 4)           # экран успокоился, пауза не прошла
    assert not quiet.take_screenshot
    after = d.process(changed(30), 6.5)         # пауза прошла — отложенный снимок
    assert after.take_screenshot
    assert after.trigger_percent == pytest.approx(100.0)
    assert not after.changed
    d.mark_saved(6.5)
    assert not d.process(changed(30), 20).take_screenshot   # больше ничего не ждём


def test_detector_reset():
    d = ChangeDetector(1, 0, 0)
    d.process(changed(0), 0)
    d.reset()
    assert not d.process(changed(100), 1).take_screenshot   # снова «первый» кадр


def test_screenshot_name_format(tmp_path):
    when = datetime(2024, 1, 15, 14, 30, 25)
    path = make_screenshot_path(tmp_path, "png", when)
    assert path.name == "screenshot_2024-01-15_14-30-25.png"
    path.write_bytes(b"")
    assert make_screenshot_path(tmp_path, "png", when).name == "screenshot_2024-01-15_14-30-25_1.png"


@pytest.mark.parametrize("fmt, pil_format", [("png", "PNG"), ("jpg", "JPEG")])
def test_save_image_formats(tmp_path, fmt, pil_format):
    img = Image.new("RGB", (40, 30), (200, 50, 50))
    folder = tmp_path / "Скриншоты" / "вложенная"   # папка создаётся автоматически
    path = save_image(img, str(folder), fmt, 80, datetime(2024, 1, 15, 14, 30, 25))
    assert path.suffix == f".{fmt}"
    with Image.open(path) as saved:
        assert saved.format == pil_format
        assert saved.size == (40, 30)


def test_find_monitor():
    monitors = [
        {"left": 0, "top": 0, "width": 3840, "height": 1080},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
        {"left": 1920, "top": 0, "width": 1920, "height": 1080},
    ]
    assert find_monitor(monitors, Region(2000, 100, 100, 100)) is monitors[2]
    assert find_monitor(monitors, Region(1800, 100, 400, 100)) is monitors[2]  # большая часть справа
    assert find_monitor(monitors, Region(-500, -500, 10, 10)) is monitors[0]   # вне экранов
